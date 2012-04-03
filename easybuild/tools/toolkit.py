##
# Copyright 2009-2012 Stijn Deweirdt, Dries Verdegem, Kenneth Hoste, Pieter De Baets, Jens Timmerman
#
# This file is part of EasyBuild,
# originally created by the HPC team of the University of Ghent (http://ugent.be/hpc).
#
# http://github.com/hpcugent/easybuild
#
# EasyBuild is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation v2.
#
# EasyBuild is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EasyBuild.  If not, see <http://www.gnu.org/licenses/>.
##
from distutils.version import LooseVersion
import os
import re

from easybuild.tools.build_log import getLog
from easybuild.tools.modules import Modules, getSoftwareRoot

log = getLog('Toolkit')

class Toolkit:
    """
    Class for compiler toolkits, consisting out of a compiler and dependencies (libraries).
    """

    def __init__(self, name, version):
        """ Initialise toolkit name version """
        self.dependencies = []
        self.vars = {}
        self.arch = None
        self.toolkit_deps = []
        self.m32flag = ''

        ## Option flags
        self.opts = {
           'usempi': False, 'cciscxx': False, 'pic': False, 'opt': False,
           'noopt': False, 'lowopt': False, 'debug': False, 'optarch':True,
           'i8': False, 'unroll': False, 'verbose': False, 'cstd': None,
           'shared': False, 'static': False, 'intel-static': False,
           'loop': False, 'f2c': False, 'no-icc': False,
           'packed-groups': False, '32bit' : False
        }

        self.name = name
        self.version = version

        # 32-bit toolkit have version that ends with '32bit'
        if self.version.endswith('32bit'):
            self.opts['32bit'] = True
            self.m32flag = " -m32"

    def _toolkitExists(self, name=None, version=None):
        """
        Verify if there exists a toolkit by this name and version
        """
        if not name:
            name = self.name
        if not version:
            version = self.version

        if self.name == 'dummy':
            return True

        return Modules().exists(name, version)

    def setOptions(self, options):
        """ Process toolkit options """
        for opt in options.keys():
            ## Only process supported opts
            if opt in self.opts:
                self.opts[opt] = options[opt]
            else:
                log.warning("Undefined toolkit option %s specified." % opt)

    def getDependencyVersion(self, dependency):
        """ Generate a version string for a dependency on a module using this toolkit """
        # Add toolkit to version string
        toolkit = ''
        if self.name != 'dummy':
            toolkit = '-%s-%s' % (self.name, self.version)
        elif self.version != 'dummy':
            toolkit = '%s' % (self.version)

        # Check if dependency is independent of toolkit
        if 'dummy' in dependency and dependency['dummy']:
            toolkit = ''

        suffix = dependency.get('suffix', '')

        if 'version' in dependency:
            return "%s%s%s" % (dependency['version'], toolkit, suffix)
        else:
            matches = Modules().available(dependency['name'], "%s%s" % (toolkit, suffix))
            # Find the most recent (or default) one
            if len(matches) > 0:
                return matches[-1]
            else:
                log.error('No toolkit version for dependency name %s (suffix %s) found'
                           % (dependency['name'], "%s%s" % (toolkit, suffix)))

    def addDependencies(self, dependencies):
        """ Verify if the given dependencies exist and add them """
        mod = Modules()
        log.debug("Adding toolkit dependencies")
        for dep in dependencies:
            if not 'tk' in dep:
                dep['tk'] = self.getDependencyVersion(dep)

            if not mod.exists(dep['name'], dep['tk']):
                log.error('No module found for dependency %s/%s' % (dep['name'], dep['tk']))
            else:
                self.dependencies.append(dep)
                log.debug('Added toolkit dependency %s' % dep)

    def prepare(self, onlymod=None):
        """
        Prepare a set of environment parameters based on name/version of toolkit
        - load modules for toolkit and dependencies
        - generate extra variables and set them in the environment

        onlymod: Boolean/string to indicate if the toolkit should only load the enviornment
        with module (True) or also set all other variables (False) like compiler CC etc
        (If string: comma separated list of variables that will be ignored).
        """
        if not self._toolkitExists():
            log.error("No module found for toolkit name '%s' (%s)" % (self.name, self.version))

        if self.name == 'dummy':
            if self.version == 'dummy':
                log.info('Toolkit: dummy mode')
            else:
                log.info('Toolkit: dummy mode, but loading dependencies')
                modules = Modules()
                modules.addModule(self.dependencies)
                modules.load()
            return

        ## Determine currently loaded modules
        modules = Modules()
        prev_loaded_modules = modules.loaded_modules()
        log.debug("Previous loaded modules: %s" % prev_loaded_modules)

        ## Load the toolkit module
        modules.addModule([(self.name, self.version)])
        modules.load()

        ## Determine modules that are dependencies of toolkit itself
        self.toolkit_deps = modules.loaded_modules()
        for dep in self.toolkit_deps:
            # remove previously loaded modules and compiler toolkit itself
            if dep in prev_loaded_modules or self.name == dep['name']:
                self.toolkit_deps.remove(dep)

        ## Load dependent modules
        modules.addModule(self.dependencies)
        modules.load()

        self._determineArchitecture()

        ## Generate the variables to be set
        self._generate_variables()

        ## set the variables
        if not (onlymod == True):
            log.debug("Variables being set: onlymod=%s" % onlymod)

            ## add LDFLAGS and CPPFLAGS from dependencies to self.vars
            self._addDependencyVariables()
            self._setVariables(onlymod)
        else:
            log.debug("No variables set: onlymod=%s" % onlymod)

    def _addDependencyVariables(self, dep=None):
        """ Add LDFLAGS and CPPFLAGS to the self.vars based on the dependencies """
        cpp_paths = ['include']
        ld_paths = ['lib64', 'lib']

        if not dep:
            deps = self.dependencies
        else:
            deps = [dep]

        for dep in deps:
            log.debug("dep: %s" % dep)
            softwareRoot = getSoftwareRoot(dep['name'])
            if not softwareRoot:
                log.error("%s was not found in environment (dep: %s)" % (dep['name'], dep))

            self._flagsForSubdirs(softwareRoot, cpp_paths, flag="-I%s", varskey="CPPFLAGS")
            self._flagsForSubdirs(softwareRoot, ld_paths, flag="-L%s", varskey="LDFLAGS")

    def _setVariables(self, dontset=None):
        """ Sets the environment variables """
        log.debug("Setting variables: dontset=%s" % dontset)

        dontsetlist = []
        if type(dontset) == str:
            dontsetlist = dontset.split(',')
        elif type(dontset) == list:
            dontsetlist = dontset

        for key, val in self.vars.items():
            if key in dontsetlist:
                log.debug("Not setting environment variable %s (value: %s)." % (key, val))
                continue

            log.debug("Setting environment variable %s to %s" % (key, val))
            os.environ[key] = val

            # also set unique named variables that can be used in Makefiles
            # - so you can have 'CFLAGS = $(SOFTVARCFLAGS)'
            # -- 'CLFLAGS = $(CFLAGS)' gives  '*** Recursive variable `CFLAGS'
            # references itself (eventually).  Stop' error
            os.environ["SOFTVAR%s" % key] = val

    def _determineArchitecture(self):
        """ Determine the CPU architecture """
        regexp = re.compile(r"^vendor_id\s+:\s*(?P<vendorid>\S+)\s*$", re.M)
        arch = regexp.search(open("/proc/cpuinfo").read()).groupdict()['vendorid']

        archd = {'GenuineIntel': 'Intel', 'AuthenticAMD': 'AMD'}
        if arch in archd:
            self.arch = archd[arch]
        else:
            log.error("Unknown architecture detected: %s" % arch)

    def _getOptimalArchitecture(self):
        """ Get options for the current architecture """
        optarchs = {'Intel':'xHOST', 'AMD':'msse3'}

        if self.arch in optarchs:
            optarch = optarchs[self.arch]
            log.info("Using %s as optarch for %s." % (optarch, self.arch))
            return optarch
        else:
            log.error("Don't know how to set optarch for %s." % self.arch)

    def _generate_variables(self):

        preparation_methods = []

        # list of preparation methods
        # number are assigned to indicate order in which they need to be run
        known_preparation_methods = {
            # compilers always go first
            '1_GCC':self.prepareGCC,
            '1_icc':self.prepareIcc, # also for ifort
            # MPI libraries
            '2_impi':self.prepareIMPI,
            '2_MPICH2':self.prepareMPICH2,
            '2_MVAPICH2':self.prepareMVAPICH2,
            '2_OpenMPI':self.prepareOpenMPI,
            '2_QLogicMPI':self.prepareQLogicMPI,
            # BLAS libraries, LAPACK, FFTW
            '3_ATLAS':self.prepareATLAS,
            '3_FFTW':self.prepareFFTW,
            '3_GotoBLAS':self.prepareGotoBLAS,
            '3_imkl':self.prepareIMKL,
            '4_LAPACK':self.prepareLAPACK,
            # BLACS, FLAME, ScaLAPACK, ...
            '5_BLACS':self.prepareBLACS,
            '5_FLAME':self.prepareFLAME,
            '6_ScaLAPACK':self.prepareScaLAPACK
        }

        # obtain list of dependency names
        depnames = []
        for dep in self.toolkit_deps:
            depnames.append(dep['name'].lower())
        log.debug("depnames: %s" % depnames)

        # figure out which preparation methods we need to run based on toolkit dependencies
        meth_keys = known_preparation_methods.keys()
        meth_keys.sort()
        for dep in depnames:
            dep_found = False
            for meth in meth_keys:
                # bit before first '_' is used for ordering
                meth_name = '_'.join(meth.split('_')[1:])
                if dep.lower() == meth_name.lower():
                    preparation_methods.append(known_preparation_methods[meth])
                    dep_found = True
                    break
            if not dep_found:
                log.error("Don't know how to prepare for toolkit dependency %s" % dep)

        log.debug("List of preparation methods: %s" % preparation_methods)

        self.vars["LDFLAGS"] = ''
        self.vars["CPPFLAGS"] = ''
        self.vars['LIBS'] = ''

        for preparation_method in preparation_methods:
            preparation_method()

        # old way, based on toolkit name
        ## TODO: get rid of this
        if not preparation_methods:
            if self.name in known_preparation_methods:
                known_preparation_methods[self.name]()
            else:
                log.error("Don't know how to prepare toolkit '%s'." % self.name)

    def prepareACML(self):
        """
        Prepare for AMD Math Core Library (ACML)
        """

        if self.opts['32bit']:
            log.error("ERROR: 32-bit not supported (yet) for ACML.")

        self._addDependencyVariables([{'name':'ACML'}])

        if os.getenv('SOFTROOTGCC'):
            compiler = 'gfortran'
        else:
            log.error("Don't know which compiler-specific subdir for ACML to use.")

        self.vars['LIBBLAS'] = "%(acml)s/%(comp)s64/lib/libacml_mv.a " \
                               "%(acml)s/%(comp)s64/lib/libacml.a -lpthread" % {
                                                                                'comp':compiler, 
                                                                                'acml':os.environ['SOFTROOTACML']
                                                                                }
        self.vars['LIBBLAS_MT'] = self.vars['LIBBLAS']

    def prepareATLAS(self):
        """
        Prepare for ATLAS BLAS/LAPACK library
        """

        self.vars['LIBBLAS'] = " -latlas -llapack -lcblas -lf77blas"
        self.vars['LIBBLAS_MT'] = " -latlas -llapack -lptcblas -lptf77blas -lpthread"

        self._addDependencyVariables({'name':'ATLAS'})

    def prepareBLACS(self):
        """
        Prepare for BLACS library
        """

        self.vars['LIBSCALAPACK'] = " -lblacsF77init -lblacs "
        self.vars['LIBSCALAPACK_MT'] = self.vars['LIBSCALAPACK']

        self._addDependencyVariables({'name':'BLACS'})

    def prepareFLAME(self):
        """
        Prepare for FLAME library
        """

        self.vars['LIBLAPACK'] += " -llapack2flame -lflame "
        self.vars['LIBLAPACK_MT'] += " -llapack2flame -lflame "

        self._addDependencyVariables({'name':'FLAME'})

    def prepareFFTW(self):
        """
        Prepare for FFTW library
        """

        suffix = ''
        if os.getenv('SOFTVERSIONFFTW').startswith('3.'):
            suffix = '3' 
        self.vars['LIBFFT'] = " -lfftw%s " % suffix
        if self.opts['usempi']:
            self.vars['LIBFFT'] += " -lfftw%s_mpi " % suffix

        self._addDependencyVariables({'name':'FFTW'})

    def prepareGCC(self, withMPI=True):
        """
        Prepare for a GCC-based compiler toolkit
        """

        if self.opts['32bit']:
            log.error("ERROR: 32-bit not supported yet for GCC based toolkits.")

        # set basic GCC options
        self.vars['CC'] = 'gcc %s' % self.m32flag
        self.vars['CXX'] = 'g++ %s' % self.m32flag
        self.vars['F77'] = 'gfortran %s ' % self.m32flag
        self.vars['F90'] = 'gfortran %s' % self.m32flag

        if self.opts['cciscxx']:
            self.vars['CXX'] = self.vars['CC']

        flags = []

        if self.opts['optarch']:
            ## difficult for GCC
            flags.append("march=native")

        flags.append(self._getOptimizationLevel())
        flags.extend(self._flagsForOptions(override={
            'i8': 'fdefault-integer-8',
            'unroll': 'funroll-loops',
            'f2c': 'ff2c',
            'loop': ['ftree-switch-conversion', 'floop-interchange',
                     'floop-strip-mine', 'floop-block']
        }))

        copts = []
        if self.opts['cstd']:
            copts.append("std=%s" % self.opts['cstd'])

        if len(flags + copts) > 0:
            self.vars['CFLAGS'] = "%s" % ('-' + ' -'.join(flags + copts))
        if len(flags) > 0:
            self.vars['CXXFLAGS'] = "%s" % ('-' + ' -'.join(flags))
        if len(flags) > 0:
            self.vars['FFLAGS'] = "%s" % ('-' + ' -'.join(flags))
        if len(flags) > 0:
            self.vars['F90FLAGS'] = "%s" % ('-' + ' -'.join(flags))

        ## to get rid of lots of problems with libgfortranbegin
        ## or remove the system gcc-gfortran
        self.vars['FLIBS']="-lgfortran"

    def prepareGotoBLAS(self):
        """
        Prepare for GotoBLAS BLAS library
        """

        self.vars['LIBBLAS'] = "-lgoto"
        self.vars['LIBBLAS_MT'] = self.vars['LIBBLAS']

        self._addDependencyVariables({'name':'GotoBLAS'})

    def prepareIcc(self):
        """
        Prepare for an icc/ifort based compiler toolkit
        """

        self.vars['CC'] = 'icc%s' % self.m32flag
        self.vars['CXX'] = 'icpc%s' % self.m32flag
        self.vars['F77'] = 'ifort%s' % self.m32flag
        self.vars['F90'] = 'ifort%s' % self.m32flag

        if self.opts['cciscxx']:
            self.vars['CXX'] = self.vars['CC']

        flags = []
        if self.opts['optarch']:
            flags.append(self._getOptimalArchitecture())

        flags.append(self._getOptimizationLevel())
        flags.extend(self._flagsForOptions(override={
            'intel-static': 'static-intel',
            'no-icc': 'no-icc'
        }))

        copts = []
        if self.opts['cstd']:
            copts.append("std=%s" % self.opts['cstd'])

        if len(flags + copts) > 0:
            self.vars['CFLAGS'] = '-' + ' -'.join(flags + copts)
        if len(flags) > 0:
            self.vars['CXXFLAGS'] = '-' + ' -'.join(flags)
        if len(flags) > 0:
            self.vars['FFLAGS'] = '-' + ' -'.join(flags)

        if LooseVersion(os.environ['SOFTVERSIONICC']) < LooseVersion('2011'):
            self.vars['LIBS'] += " -liomp5 -lguide -lpthread"
        else:
            self.vars['LIBS'] += " -liomp5 -lpthread"

    def prepareIMKL(self):
        """
        Prepare toolkit for IMKL: Intel Math Kernel Library
        """

        mklRoot = os.getenv('MKLROOT')
        if not mklRoot:
            log.error("MKLROOT not found in environment")

        # For more inspiration: see http://software.intel.com/en-us/articles/intel-mkl-link-line-advisor/

        libsuffix = "_lp64"
        libsuffixsl = "_lp64"
        libdir = "em64t"
        if self.opts['32bit']:
            libsuffix = ""
            libsuffixsl = "_core"
            libdir = "32"

        self.vars['LIBLAPACK'] = \
            "-Wl,--start-group %(mkl)s/lib/%(libdir)s/libmkl_intel%(libsuffix)s.a " \
            "%(mkl)s/lib/%(libdir)s/libmkl_sequential.a " \
            "%(mkl)s/lib/%(libdir)s/libmkl_core.a -Wl,--end-group" % {'mkl':mklRoot,
                                                                      'libdir':libdir,
                                                                      'libsuffix':libsuffix
                                                                     }
        self.vars['LIBBLAS'] = self.vars['LIBLAPACK']
        self.vars['LIBLAPACK_MT'] = \
            "-Wl,--start-group %(mkl)s/lib/%(libdir)s/libmkl_intel%(libsuffix)s.a " \
            "%(mkl)s/lib/%(libdir)s/libmkl_intel_thread.a " \
            "%(mkl)s/lib/%(libdir)s/libmkl_core.a -Wl,--end-group " \
            "-liomp5 -lpthread" % {'mkl':mklRoot,
                                   'libdir':libdir,
                                   'libsuffix':libsuffix
                                  }
        self.vars['LIBBLAS_MT'] = self.vars['LIBLAPACK_MT']
        self.vars['LIBSCALAPACK'] = \
            "%(mkl)s/lib/%(libdir)s/libmkl_scalapack%(libsuffixsl)s.a " \
            "%(mkl)s/lib/%(libdir)s/libmkl_solver%(libsuffix)s_sequential.a " \
            "-Wl,--start-group  %(mkl)s/lib/%(libdir)s/libmkl_intel%(libsuffix)s.a " \
            "%(mkl)s/lib/%(libdir)s/libmkl_sequential.a " \
            "%(mkl)s/lib/%(libdir)s/libmkl_core.a " \
            "%(mkl)s/lib/%(libdir)s/libmkl_blacs_intelmpi%(libsuffix)s.a -Wl,--end-group" % {'mkl':mklRoot,
                                                                                            'libdir':libdir,
                                                                                            'libsuffix':libsuffix,
                                                                                            'libsuffixsl':libsuffixsl
                                                                                           }

        if self.opts['packed-groups']: #we pack groups toghether, since some tools like pkg-utils don't work well with them
            for i in ['LIBLAPACK', 'LIBBLAS', 'LIBLAPACK_MT', 'LIBSCALAPACK' ]:
                self.vars[i] = self.vars[i].replace(" ", ",").replace("-Wl,--end-group", "--end-group")

        lib = self.vars['LIBSCALAPACK']
        lib = lib.replace('libmkl_solver%s_sequential' % libsuffix, 'libmkl_solver')
        lib = lib.replace('libmkl_sequential', 'libmkl_intel_thread') + ' -liomp5 -lpthread'
        self.vars['LIBSCALAPACK_MT'] = lib

        # Exact paths/linking statements depend on imkl version
        if LooseVersion(os.environ['SOFTVERSIONIMKL']) < LooseVersion('10.3'):
            if self.opts['32bit']:
                mklld = ['lib/32']
            else:
                mklld = ['lib/em64t']
            mklcpp = ['include', 'include/fftw']
        else:
            if self.opts['32bit']:
                log.error("32-bit libraries not supported yet for IMKL v%s (> v10.3)" % os.environ("SOFTROOTIMKL"))

            mklld = ['lib/intel64', 'mkl/lib/intel64']
            mklcpp = ['mkl/include', 'mkl/include/fftw']

            static_vars = ['LIBBLAS', 'LIBBLAS_MT', 'LIBLAPACK', 'LIBLAPACK_MT', 'LIBSCALAPACK', 'LIBSCALAPACK_MT']
            for var in static_vars:
                self.vars[var] = self.vars[var].replace('/lib/em64t/', '/mkl/lib/intel64/')

        # Linker flags
        self._flagsForSubdirs(mklRoot, mklld, flag="-L%s", varskey="LDFLAGS")
        self._flagsForSubdirs(mklRoot, mklcpp, flag="-I%s", varskey="CPPFLAGS")

        if os.getenv('SOFTROOTGCC'):
            if not (os.getenv('SOFTROOTGCC') or os.getenv('SOFTROOTGCC')):
                for var in ['LIBLAPACK', 'LIBLAPACK_MT', 'LIBSCALAPACK', 'LIBSCALAPACK_MT']:
                    self.vars[var] = self.vars[var].replace('mkl_intel_lp64', 'mkl_gf_lp64')
            else:
                log.error("Toolkit preparation with both GCC and Intel compilers loaded is not supported.")

    def prepareIMPI(self):
        """
        Prepare for Intel MPI library
        """

        if os.getenv('SOFTROOTICC') and os.getenv('SOFTROOTIFORT') and not os.getenv('SOFTROOTGCC'):
            # Intel-based toolkit

            self.vars['MPICC'] = 'mpiicc %s' % self.m32flag
            self.vars['MPICXX'] = 'mpiicpc %s' % self.m32flag
            self.vars['MPIF77'] = 'mpiifort %s' % self.m32flag
            self.vars['MPIF90'] = 'mpiifort %s' % self.m32flag

            if self.opts['usempi']:
                for i in ['CC', 'CXX', 'F77', 'F90']:
                    self.vars[i] = self.vars["MPI%s" % i]

            # used by mpicc and mpicxx to actually use mpiicc and mpiicpc
            self.vars['I_MPI_CXX'] = "icpc"
            self.vars['I_MPI_CC'] = "icc"

            if self.opts['cciscxx']:
                self.vars['MPICXX'] = self.vars['MPICC']

        else:
            # other compilers (e.g. GCC) with Intel MPI
            self.vars['MPICC'] = 'mpicc -cc=%s %s ' % (self.vars['CC'], self.m32flag)
            self.vars['MPICXX'] = 'mpicxx -cxx=%s %s ' % (self.vars['CXX'], self.m32flag)
            self.vars['MPIF77'] = 'mpif77 -fc=%s %s ' % (self.vars['F77'], self.m32flag)
            self.vars['MPIF90'] = 'mpif90 -fc=%s %s ' % (self.vars['F90'], self.m32flag)

    def prepareQLogicMPI(self):

        ## QLogic specific
        self.vars['MPICC'] = 'mpicc -cc="%s"' % os.getenv('CC')
        self.vars['MPICXX'] = 'mpicxx -CC="%s"' % os.getenv('CXX')
        self.vars['MPIF77'] = 'mpif77 -fc="%s"' % os.getenv('F77')
        self.vars['MPIF90'] = 'mpif90 -f90="%s"' % os.getenv('F90')

        if self.opts['usempi']:
            for i in ['CC', 'CXX', 'F77', 'F90']:
                self.vars[i] = self.vars["MPI%s" % i]

    def prepareLAPACK(self):
        """
        Prepare for LAPACK library
        """

        self.vars['LIBLAPACK'] = "%s -llapack" % self.vars['LIBBLAS']
        self.vars['LIBLAPACK_MT'] = "%s -llapack -lpthread" % self.vars['LIBBLAS_MT']

        self._addDependencyVariables({'name':'LAPACK'})

    def prepareMPICH2(self):
        """
        Prepare for MPICH2 MPI library (e.g. ScaleMP's version)
        """
        if "vSMP" in os.getenv('SOFTVERSIONMPICH2'):
            # ScaleMP MPICH specific
            self.vars['MPICC'] = 'mpicc -cc="%s %s"' % (os.getenv('CC'), self.m32flag)
            self.vars['MPICXX'] = 'mpicxx -CC="%s %s"' % (os.getenv('CXX'), self.m32flag)
            self.vars['MPIF77'] = 'mpif77 -fc="%s %s"' % (os.getenv('F77'), self.m32flag)
            self.vars['MPIF90'] = 'mpif90 -f90="%s %s"' % (os.getenv('F90'), self.m32flag)

            if self.opts['cciscxx']:
                self.vars['MPICXX'] = self.vars['MPICC']

            if self.opts['usempi']:
                for i in ['CC', 'CXX', 'F77', 'F90']:
                    self.vars[i] = self.vars["MPI%s" % i]
        else:
            self.log.error("Don't know how to prepare for a non-ScaleMP MPICH2 library.")

    def prepareSimpleMPI(self):
        """
        Prepare for 'simple' MPI libraries (e.g. MVAPICH2, OpenMPI)
        """

        self.vars['MPICC'] = 'mpicc %s' % self.m32flag
        self.vars['MPICXX'] = 'mpicxx %s' % self.m32flag
        self.vars['MPIF77'] = 'mpif77 %s' % self.m32flag
        self.vars['MPIF90'] = 'mpif90 %s' % self.m32flag

        if self.opts['cciscxx']:
            self.vars['MPICXX'] = self.vars['MPICC']

        if self.opts['usempi']:
            for i in ['CC', 'CXX', 'F77', 'F90']:
                self.vars[i] = self.vars["MPI%s" % i]

    def prepareMVAPICH2(self):
        """
        Prepare for MVAPICH2 MPI library
        """
        self.prepareSimpleMPI()

    def prepareOpenMPI(self):
        """
        Prepare for OpenMPI MPI library
        """
        self.prepareSimpleMPI()

    def prepareScaLAPACK(self):
        """
        Prepare for ScaLAPACK library
        """
        self.vars['LIBSCALAPACK'] += " -lscalapack"
        self.vars['LIBSCALAPACK_MT'] += " %s -lpthread" % self.vars['LIBSCALAPACK']

        self._addDependencyVariables({'name':'ScaLAPACK'})

    def _getOptimizationLevel(self):
        """ Default is 02, but set it explicitly (eg -g otherwise becomes -g -O0)"""
        if self.opts['noopt']:
            return 'O0'
        elif self.opts['opt']:
            return 'O3'
        elif self.opts['lowopt']:
            return 'O1'
        else:
            return 'O2'

    def _flagsForOptions(self, override=None):
        """
        Parse options to flags.
        """
        flags = []

        flagOptions = {
            'pic': 'fPIC', 'debug': 'g', 'i8': 'i8',
            'static': 'static', 'unroll': 'unroll', 'verbose': 'v', 'shared': 'shared',
        }
        if override:
            flagOptions.update(override)

        for key in flagOptions.keys():
            if self.opts[key]:
                newFlags = flagOptions[key]
                if type(newFlags) == list:
                    flags.extend(newFlags)
                else:
                    flags.append(newFlags)

        return flags

    def _flagsForSubdirs(self, base, subdirs, flag="-L%s", varskey=None):
        """ Generate include flags to pass to the compiler """
        flags = []
        for subdir in subdirs:
            directory = os.path.join(base, subdir)
            if os.path.isdir(directory):
                flags.append(flag % directory)
            else:
                log.warning("Directory %s was not found" % directory)

        if not varskey in self.vars:
            self.vars[varskey] = ''
        self.vars[varskey] += ' ' + ' '.join(flags)
