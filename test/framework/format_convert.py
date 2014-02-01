"""
Unit tests for easyconfig/format/convert.py

@author: Stijn De Weirdt (Ghent University)
"""
import re

from easybuild.tools.convert import get_convert_class, ListOfStrings
from easybuild.tools.convert import DictOfStrings, ListOfStringsAndDictOfStrings
from easybuild.framework.easyconfig.format.convert import Dependency, Patch, Patches

from easybuild.framework.easyconfig.format.version import VersionOperator, ToolchainVersionOperator

from unittest import TestCase, TestLoader, main


class ConvertTest(TestCase):
    """Test the license"""

    def test_subclasses(self):
        """Check if a number of common convert classes can be found"""
        for convert_class in ListOfStrings, DictOfStrings, ListOfStringsAndDictOfStrings:
            self.assertEqual(get_convert_class(convert_class.__name__), convert_class)

    def assertErrorRegex(self, error, regex, call, *args):
        """ convenience method to match regex with the error message """
        try:
            call(*args)
            self.assertTrue(False)  # this will fail when no exception is thrown at all
        except error, err:
            if hasattr(err, 'msg'):
                msg = getattr(err, 'msg')
            elif hasattr(err, 'message'):
                msg = getattr(err, 'message')

            res = re.search(regex, msg)
            if not res:
                print "err: %s" % err
            self.assertTrue(res)

    def test_listofstrings(self):
        """Test list of strings"""
        # test default separators
        self.assertEqual(ListOfStrings.SEPARATOR_LIST, ',')

        dest = ['a', 'b']
        txt = ListOfStrings.SEPARATOR_LIST.join(dest)

        res = ListOfStrings(txt)

        self.assertEqual(res, dest)
        self.assertEqual(str(res), txt)

        # retest with space separated separator
        res = ListOfStrings(txt.replace(ListOfStrings.SEPARATOR_LIST, ListOfStrings.SEPARATOR_LIST + ' '))
        self.assertEqual(res, dest)

    def test_dictofstrings(self):
        """Test dict of strings"""
        # test default separators
        self.assertEqual(DictOfStrings.SEPARATOR_DICT, ';')
        self.assertEqual(DictOfStrings.SEPARATOR_KEY_VALUE, ':')

        # start with simple one because the conversion to string is ordered
        dest = {'a':'b'}
        txt = DictOfStrings.SEPARATOR_KEY_VALUE.join(dest.items()[0])

        res = DictOfStrings(txt)
        self.assertEqual(res, dest)
        self.assertEqual(str(res), txt)

        # test with auto convert list to dict
        class Tmp(DictOfStrings):
            MIXED_LIST = ['first']
            __str__ = DictOfStrings.__str__

        dest2 = {'first':'first_value'}
        dest2.update(dest)
        txt2 = DictOfStrings.SEPARATOR_DICT.join([dest2['first'], txt])
        res = Tmp(txt2)
        self.assertEqual(res, dest2)
        self.assertEqual(str(res), txt2)

        # retest with space separated separator
        txt2 = txt.replace(DictOfStrings.SEPARATOR_KEY_VALUE, DictOfStrings.SEPARATOR_KEY_VALUE + ' ')
        res = ListOfStrings(txt2.replace(DictOfStrings.SEPARATOR_DICT, DictOfStrings.SEPARATOR_DICT + ' '))


        # more complex one
        dest = {'a':'b', 'c':'d'}
        tmp = [DictOfStrings.SEPARATOR_KEY_VALUE.join(item) for item in dest.items()]
        txt = DictOfStrings.SEPARATOR_DICT.join(tmp)

        res = DictOfStrings(txt)
        self.assertEqual(res, dest)

        # test ALLOWED_KEYS
        class Tmp(DictOfStrings):
            ALLOWED_KEYS = ['x']

        self.assertErrorRegex(ValueError, "allowed", Tmp, txt)

    def test_listofstringsanddictofstrings(self):
        """Test ListOfStringsAndDictOfStrings"""
        # test default separators
        self.assertEqual(ListOfStringsAndDictOfStrings.SEPARATOR_LIST, ',')
        self.assertEqual(ListOfStringsAndDictOfStrings.SEPARATOR_DICT, ';')
        self.assertEqual(ListOfStringsAndDictOfStrings.SEPARATOR_KEY_VALUE, ':')

        txt = "a,b,c:d"
        dest = ['a', 'b', {'c':'d'}]

        res = ListOfStringsAndDictOfStrings(txt)
        self.assertEqual(res, dest)
        self.assertEqual(str(res), txt)

        # retest with space separated separator
        txt2 = txt.replace(ListOfStringsAndDictOfStrings.SEPARATOR_LIST,
                           ListOfStringsAndDictOfStrings.SEPARATOR_LIST + ' ')
        txt2 = txt2.replace(ListOfStringsAndDictOfStrings.SEPARATOR_KEY_VALUE,
                            ListOfStringsAndDictOfStrings.SEPARATOR_KEY_VALUE + ' ')
        res = ListOfStringsAndDictOfStrings(txt2.replace(ListOfStringsAndDictOfStrings.SEPARATOR_DICT,
                                                         ListOfStringsAndDictOfStrings.SEPARATOR_DICT + ' '))

        # larger test
        txt = "a,b,c:d;e:f,g,h,i:j"
        dest = ['a', 'b', {'c':'d', 'e': 'f'}, 'g', 'h', {'i': 'j'}]

        res = ListOfStringsAndDictOfStrings(txt)
        self.assertEqual(res, dest)

        # test ALLOWED_KEYS
        class Tmp(ListOfStringsAndDictOfStrings):
            ALLOWED_KEYS = ['x']

        self.assertErrorRegex(ValueError, "allowed", Tmp, txt)

    def test_dependency(self):
        """Test Dependency class"""
        versop_str = '>= 1.5'
        tc_versop_str = 'GCC >= 3.0'

        versop = VersionOperator(versop_str)
        tc_versop = ToolchainVersionOperator(tc_versop_str)

        txt = Dependency.SEPARATOR_DEP.join([versop_str])
        dest = {'versop':versop}
        res = Dependency(txt)
        self.assertEqual(dest, res)
        self.assertEqual(str(res), txt)

        txt = Dependency.SEPARATOR_DEP.join([versop_str, tc_versop_str])
        dest = {'versop':versop, 'tc_versop':tc_versop}
        res = Dependency(txt)
        self.assertEqual(dest, res)
        self.assertEqual(str(res), txt)

    def test_patch(self):
        """Test Patch class"""

        # filename;level:<int>;dest:<string>
        dest = {
            'filename':'/some/path',
            'level':1,
            'dest':'somedir',
        }
        newdest = {
            'sep':DictOfStrings.SEPARATOR_DICT,
            'dsep':DictOfStrings.SEPARATOR_KEY_VALUE,
        }
        newdest.update(dest)
        txt = "%(filename)s%(sep)slevel%(dsep)s%(level)s%(sep)sdest%(dsep)s%(dest)s" % newdest

        res = Patch(txt)
        self.assertEqual(res, dest)

    def test_patches(self):
        """Test Patches"""

        dest = [
            {'filename':'fn1',
             'level': 1,
             },
            {'filename':'fn2'
             },
            {'filename':'fn3',
             'dest':'somedir',
             }
        ]
        newdest = {
            'lsep':ListOfStrings.SEPARATOR_LIST,
            'sep':DictOfStrings.SEPARATOR_DICT,
            'dsep':DictOfStrings.SEPARATOR_KEY_VALUE,
        }

        tmpl = [
            "%(filename)s%(sep)slevel%(dsep)s%(level)s",
            "%(filename)s",
            "%(filename)s%(sep)sdest%(dsep)s%(dest)s",
        ]

        txtlist = []
        for idx, p in enumerate(dest):
            n = {}
            n.update(newdest)
            n.update(p)

            txtlist.append(tmpl[idx] % n)

        res = Patches(newdest['lsep'].join(txtlist))
        self.assertEqual(res, dest)


def suite():
    """ returns all the testcases in this module """
    return TestLoader().loadTestsFromTestCase(ConvertTest)


if __name__ == '__main__':
    # logToScreen(enable=True)
    # setLogLevelDebug()
    main()
