#!/usr/bin/env python

import os
import sys
from math import fabs
from math import sqrt

import _nvtest.util.tty as tty
from _nvtest.error import TestDiffed

version = "3.1"

# version 2.0 includes grouping for tensors and vectors
# version 2.0 includes support for mathematical norms (Linf, L1, L2)
# version 2.0 changed the floor to ignore if both |v1| < floor and |v2| < floor
# version 3 changed the exit status when there is a diff to a two, 2
# version 3.1 changed to raise a HisDiffError if files diffed

# the "header" types
POINTID = 0
POINTVAR = 1
MATID = 2
MATVAR = 3
GLOBVAR = 4
POINTVAR_UNITS = 5
MATVAR_UNITS = 6
GLOBVAR_UNITS = 7

# For upgrading from 2->3
# The original hisdiff script was written in Python2 and relied on free
# functions from the string module for upper, lower, etc. In Python3, the
# string module does not provide those free functions, they are now methods of
# string objects. Additionally, reading in the binary hisplot format results in
# bytes in Python3 and not str. The helpers below decode the bytes and provide
# implementations of the string free functions.


class byte_string:
    @staticmethod
    def decode_byte_str(byte_str):
        try:
            return byte_str.decode("utf-8")
        except AttributeError:
            return str(byte_str)

    @staticmethod
    def upper(byte_str):
        byte_string.decode_byte_str(byte_str).upper()

    @staticmethod
    def lower(byte_str):
        byte_string.decode_byte_str(byte_str).lower()

    @staticmethod
    def strip(byte_str):
        byte_string.decode_byte_str(byte_str).strip()

    @staticmethod
    def rstrip(byte_str):
        byte_string.decode_byte_str(byte_str).rstrip()

    @staticmethod
    def lstrip(byte_str):
        byte_string.decode_byte_str(byte_str).lstrip()

    @staticmethod
    def split(byte_str, sep=None):
        byte_string.decode_byte_str(byte_str).split(sep)

    @staticmethod
    def join(list_of_byte_str, sep):
        sep.join(byte_string.decode_byte_str(_) for _ in list_of_byte_str)


# The original hisdiff had a global logging state.  we duplicate it here
tee = tty.tee()


def his_diff(
    file1,
    file2,
    *,
    cmdfile=None,
    overlap_times=False,
    allow_name_mismatch=False,
    nosymm=False,
    interpolate=False,
):
    """Reads CTH HISPLT binary history files and compares the floating point
    variables between them.

    Parameters
    ----------
    file1, file2 : str
        Paths to files to compare
    cmdfile : str
        Path to hisdiff command file
    overlap_times :  bool
        Compare the data at the simulation times that overlap.
    allow_name_mismatch : bool
        Do not issue a warning if a variable exists in the first file but not
        the second file. Also, do not issue a warning if a variable exists in
        the second file but not the first. Excluded variables are not
        reported.
    nosymm : bool
        No symmetric variable checking. Normally, if a variable exists in the
        second file but not the first, a warning is issued. This switch turns
        off that check. Excluded variables are not reported.
    interpolate : bool
        When taking the norm the second file's values are interpolated onto
        those of the first file and the norm is taken with those interpolated
        values on only values that overlap.

    Notes
    -----
    The first form (with two history files) does a comparison between the two
    files. The second form (with only one history file) scans the file for
    maximum and minimum variable values and writes these values to stdout in
    the form of a valid command input file.

    In diff mode, if the files differ, this script raises a HisDiffError

    Version 2.0 added differencing using mathematical norms over time. You
    can now specify "L1", "L2", or "Linf" as the norm used to determine if a
    variable is different between the two files. This specification is placed
    in the same location as "floor <number>" and "rel <number>". The old,
    individual point norm can be specified with the string "Individual".

    Version 2.0 added some knowledge of vectors, tensors and quaternions.
    These variables are now recognized and norms are applied to all the
    components at once. If needed, you can refer to a "group" using the base
    name, such as "VELOCITY" for the vector ["VELOCITY-X","VELOCITY-Y"]. Note
    that by default, groups are differenced rather than their components.

    """
    tee.open("hisdiff.out")

    if not os.path.isfile(file1):
        raise ValueError(f"hisdiff: file not found: {file1}")
    tee.write("hisdiff: reading file " + file1)
    f1 = FileData(file1)

    if file2 is None:
        echo_summary(f1)
        return

    if not os.path.isfile(file2):
        raise ValueError(f"hisdiff: file not found: {file2}")
    tee.write("hisdiff: reading file " + file2)
    f2 = FileData(file2)

    tee.write(
        f"""
   *****************************************************************
     HISDIFF  HISDIFF  HISDIFF  HISDIFF  HISDIFF  HISDIFF  HISDIFF

                      Version: {version}
                      Author : rrdrake@sandia.gov

     HISDIFF  HISDIFF  HISDIFF  HISDIFF  HISDIFF  HISDIFF  HISDIFF
   *****************************************************************"""
    )
    specs = TotalSpecs()

    if overlap_times:
        specs.set_overlap_times(1)

    if interpolate:
        specs.set_interpolate_times(1)

    if cmdfile is not None:
        if not os.path.isfile(cmdfile):
            raise ValueError(f"hisdiff: command file not found: {cmdfile}")
        tee.write(f"hisdiff: reading command file {cmdfile}")
        try:
            parse_command_file(specs, cmdfile)
        except IOError as e:
            raise HisDiffError(f"Could not read command file: {e.args[0]}")
        except ParseError as e:
            raise HisDiffError(f"{e.args[0]}")

    tee.write("  FILE 1:", f1.filename)
    tee.write("   Title:", f1.title)
    tee.write(
        "     Points =",
        len(f1.get_header_list(POINTID)),
        "Point vars =",
        len(f1.get_header_list(POINTVAR)),
        "Materials =",
        len(f1.get_header_list(MATID)),
        "Material vars =",
        len(f1.get_header_list(MATVAR)),
        "Global vars =",
        len(f1.get_header_list(GLOBVAR)),
    )
    tee.write("  FILE 2:", f2.filename)
    tee.write("   Title:", f2.title)
    tee.write(
        "     Points =",
        len(f2.get_header_list(POINTID)),
        "Point vars =",
        len(f2.get_header_list(POINTVAR)),
        "Materials =",
        len(f2.get_header_list(MATID)),
        "Material vars =",
        len(f2.get_header_list(MATVAR)),
        "Global vars =",
        len(f2.get_header_list(GLOBVAR)),
    )

    if not allow_name_mismatch:
        varwarn(specs, POINT_SPECS, POINTVAR, f1, f2, nosymm)
        varwarn(specs, MATERIAL_SPECS, MATVAR, f1, f2, nosymm)
        varwarn(specs, GLOBAL_SPECS, GLOBVAR, f1, f2, nosymm)

    varload(specs, POINT_SPECS, POINTVAR, f1, f2)
    varload(specs, MATERIAL_SPECS, MATVAR, f1, f2)
    varload(specs, GLOBAL_SPECS, GLOBVAR, f1, f2)

    specs.output(
        tee,
        f1.get_group_extensions(POINTVAR),
        f1.get_group_extensions(MATVAR),
        f1.get_group_extensions(GLOBVAR),
    )

    ilist = IndexLists()
    diffs = ilist.build_lists(specs, f1, f2)
    diffs += process_tolerances(ilist, f1, f2, interpolate)

    if diffs:
        tee.write("hisdiff: Files are different")
    else:
        tee.write("hisdiff: Files are the same")

    tee.close()

    if diffs:
        raise HisDiffError("files are different")

    return


############################################################################


class FileData:
    def __init__(self, filename):
        self.title = ""
        self.filename = filename
        self.idstring = filename

        # make this false to avoid removing duplicates
        self.nodups = 1

        # indexed by POINTID, POINTVAR, MATID, MATVAR, GLOBVAR,
        # POINTVAR_UNITS, MATVAR_UNITS, GLOBVAR_UNITS;  the lists contain ids
        # and variable names for each type of data; the point ids are actually
        # pairs of (id,type)
        self.header = [[], [], [], [], [], [], [], []]

        self.groups = [None, {}, None, {}, {}, None, None, None]
        self.group_xlist = [None, {}, None, {}, {}, None, None, None]
        self.group_indexes = [None, {}, None, {}, {}, None, None, None]
        self.combined = [None, [], None, [], [], None, None, None]

        self.cycles = []
        self.times = []
        self.timesteps = []
        self.cputimes = []

        # each entry is a list of length len(self.header[POINTID])
        # and each of those a list of length len(self.header[POINTVAR])
        self.point_values = []

        # each entry is a list of length len(self.header[MATID])
        # and each of those a list of length len(self.header[MATVAR])
        self.mat_values = []

        # each entry is a list of length len(self.header[GLOBVAR])
        self.glob_values = []

        errstr = self._read_file(filename)
        if errstr:
            raise IOError(errstr)

    def get_header_list(self, header_type):
        """
        Use POINTID, POINTVAR, POINTVAR_UNITS, MATID, MATVAR, MATVAR_UNITS,
        GLOBVAR, or GLOBVAR_UNITS.  Returns a list of (id,type) for POINTID,
        ids for MATID, and string names for others.
        """
        return self.header[header_type]

    def get_group_dict(self, header_type):
        """
        Returns a dictionary mapping group names to a list of component
        variable names.  Eg, 'VELOCITY' -> ['VELOCITY_X','VELOCITY_Y'].
        """
        return self.groups[header_type]

    def get_group_extensions(self, header_type):
        """
        Returns a dictionary mapping group names to a list of component
        extension names.  Eg, 'VELOCITY' -> ['X','Y'].
        """
        return self.group_xlist[header_type]

    def get_header_combined_list(self, header_type):
        """
        The recognized group names are extracted and merged uniquely with the
        non-group (or scalar) variable names.  Components of a group are not
        included.
        """
        return self.combined[header_type]

    def get_name_index(self, header_type, var_name):
        """
        Finds the given name in the header list and returns its index.
        If the name is a group name, then a list of indexes is returned.
        If the name is not found, None is returned.
        """
        if var_name in self.groups[header_type]:
            return self.group_indexes[header_type][var_name]
        for i in range(len(self.header[header_type])):
            n = self.header[header_type][i]
            if var_name == n:
                return i
        return None

    def get_units_list(self, header_type):
        """
        Use POINTVAR, MATVAR, or GLOBVAR.  Returns a list of unit strings for
        the given variable type.
        """
        if header_type == POINTVAR:
            return self.header[POINTVAR_UNITS]
        elif header_type == MATVAR:
            return self.header[MATVAR_UNITS]

        assert (
            header_type == GLOBVAR
        ), "header_type must be POINTVAR, MATVAR, or GLOBVAR"
        return self.header[GLOBVAR_UNITS]

    def get_time_values(self):
        return self.times

    def get_values(self, var_header_type, var_index, id_index=None, offsets=None):
        """
        The 'var_header_type' can be POINTVAR, MATVAR, or GLOBVAR.
        The 'id_index' must be supplied for POINTVAR and MATVAR.
        Returns a list of variable values of the given type of data for the
        given variable index for the given id index over all time steps.
        If 'offsets' is given, it is a list of time step offsets to be
        collected and returned.
        If 'var_index' is a list, then the values for each variable index
        are appended sequentially to the final list to be returned.
        """
        vals = []
        if type(var_index) in [list, tuple]:
            iL = var_index
        else:
            iL = [var_index]

        for vi in iL:
            if var_header_type == POINTVAR:
                assert id_index >= 0 and id_index < len(self.header[POINTID])
                assert vi >= 0 and vi < len(self.header[POINTVAR])
                if offsets is None:
                    for pL in self.point_values:
                        vals.append(pL[id_index][vi])
                else:
                    for off in offsets:
                        vals.append(self.point_values[off][id_index][vi])

            elif var_header_type == MATVAR:
                assert id_index >= 0 and id_index < len(self.header[MATID])
                assert vi >= 0 and vi < len(self.header[MATVAR])
                if offsets is None:
                    for mL in self.mat_values:
                        vals.append(mL[id_index][vi])
                else:
                    for off in offsets:
                        vals.append(self.mat_values[off][id_index][vi])

            else:
                assert var_header_type == GLOBVAR
                assert vi >= 0 and vi < len(self.header[GLOBVAR])
                if offsets is None:
                    for gL in self.glob_values:
                        vals.append(gL[vi])
                else:
                    for off in offsets:
                        vals.append(self.glob_values[off][vi])

        return vals

    def _assert(self, boolean):
        if not boolean:
            raise IOError("Database file corrupt?")

    def _read_file(self, filename):
        return self._read_hisplt(filename)

    HISPLT_title_length = 80
    HISPLT_QA_length = 38
    HISPLT_valid_codes = [-100, -101, -102, -103]

    def _read_hisplt(self, filename):
        """ """
        import array

        # Look at the first fortran record for a valid (negative) code.
        # Try four and eight byte fortran padding and little and big endian.
        # Raises an IOError if the platform could not be (uniquely) determined.

        fp = open(filename, "rb")
        fp.read(4 + 3 * 4)  # 4 byte padding plus 3 floats
        sz4 = fp.read(4)
        sz8 = fp.read(4)
        fp.close()

        okcnt = 0
        i = array.array("i")
        i.frombytes(sz4)
        if i[0] in FileData.HISPLT_valid_codes:
            paddingsize = 4
            swapbytes = 0
            okcnt = okcnt + 1
        i = array.array("i")
        i.frombytes(sz8)
        if i[0] in FileData.HISPLT_valid_codes:
            paddingsize = 8
            swapbytes = 0
            okcnt = okcnt + 1
        i = array.array("i")
        i.frombytes(sz4)
        i.byteswap()
        if i[0] in FileData.HISPLT_valid_codes:
            paddingsize = 4
            swapbytes = 1
            okcnt = okcnt + 1
        i = array.array("i")
        i.frombytes(sz8)
        i.byteswap()
        if i[0] in FileData.HISPLT_valid_codes:
            paddingsize = 8
            swapbytes = 1
            okcnt = okcnt + 1

        if okcnt == 0:
            raise IOError(
                "*** error: could not determine fortran padding "
                + "and byte order for this file (no valid code found in first "
                + "record)"
            )
        elif okcnt > 1:
            raise IOError(
                "*** error: could not determine fortran padding "
                + "and byte order for this file (more than one possiblility)"
            )

        got_counts = 0
        got_var_names = 0
        num_dumps = 0
        have_cycle = 0
        have_time = 0
        have_dt = 0
        have_cpu = 0

        fp = open(filename, "rb")

        num_points = None
        num_point_vars = None
        num_mats = None
        num_mat_vars = None
        num_glob_vars = None

        while 1:
            pad = fp.read(paddingsize)
            if len(pad) != paddingsize:
                break

            # read the first three floats
            ra = array.array("f")
            ra.fromfile(fp, 3)
            if swapbytes:
                ra.byteswap()

            # then read the dump number/code
            icode = array.array("i")
            icode.fromfile(fp, 1)
            if swapbytes:
                icode.byteswap()
            icode = icode[0]

            if icode == -100:
                # read past the last 3 entries & padding
                fp.read(12 + 2 * paddingsize)
                if self.title:
                    self.title = self.title + "\n"
                self.title = self.title + byte_string.strip(
                    fp.read(FileData.HISPLT_title_length)
                )

            elif icode == -101:
                if num_dumps == 0:
                    # read past the last 3 entries & padding
                    fp.read(12 + 2 * paddingsize)
                    fp.read(FileData.HISPLT_QA_length)
                else:
                    # read through a sequence of variable values;  num_dumps may
                    # not be the right trigger, but it seems to work on a few
                    # test cases
                    a = array.array("f")
                    a.fromfile(
                        fp,
                        num_points * num_point_vars
                        + num_mats * num_mat_vars
                        + num_glob_vars,
                    )
                    fp.read(2 * paddingsize)
                    fp.read(FileData.HISPLT_QA_length)

            elif icode == -102:
                # read past the last 3 entries & padding
                fp.read(12 + 2 * paddingsize)
                cnts = array.array("i")
                cnts.fromfile(fp, 5)
                if swapbytes:
                    cnts.byteswap()
                num_points = cnts[0]
                num_mats = cnts[1]
                num_point_vars = cnts[2]
                num_mat_vars = cnts[3]
                num_glob_vars = cnts[4]
                # print "num_points", num_points, "num_mats", num_mats, \
                #      "num_point_vars", num_point_vars, \
                #      "num_mat_vars", num_mat_vars, "num_glob_vars", num_glob_vars

                got_counts = 1

            elif icode == -103:
                if not got_counts:
                    fp.close()
                    raise IOError(
                        "*** error: variable names cannot come before "
                        + "variable counts (corrupt file?)"
                    )

                # it appears as though values for all the variables are written to
                # this fortran record even though the names have not been read yet.
                # read skip through them to get to the end of the current record
                a = array.array("f")
                a.fromfile(
                    fp,
                    num_points * num_point_vars
                    + num_mats * num_mat_vars
                    + num_glob_vars,
                )

                fp.read(2 * paddingsize)  # read past padding

                for i in range(num_point_vars):
                    L = byte_string.split(fp.read(16))
                    if len(L) > 0:
                        self.header[POINTVAR].append(L[0])
                    else:
                        self.header[POINTVAR].append("")
                for i in range(num_mat_vars):
                    L = byte_string.split(fp.read(16))
                    if len(L) > 0:
                        self.header[MATVAR].append(L[0])
                    else:
                        self.header[MATVAR].append("")
                for i in range(num_glob_vars):
                    L = byte_string.split(fp.read(16))
                    if len(L) > 0:
                        self.header[GLOBVAR].append(L[0])
                    else:
                        self.header[GLOBVAR].append("")

                for i in range(num_point_vars):
                    L = byte_string.split(fp.read(16))
                    if len(L) > 0:
                        self.header[POINTVAR_UNITS].append(L[0])
                    else:
                        self.header[POINTVAR_UNITS].append("")
                for i in range(num_mat_vars):
                    L = byte_string.split(fp.read(16))
                    if len(L) > 0:
                        self.header[MATVAR_UNITS].append(L[0])
                    else:
                        self.header[MATVAR_UNITS].append("")
                for i in range(num_glob_vars):
                    L = byte_string.split(fp.read(16))
                    if len(L) > 0:
                        self.header[GLOBVAR_UNITS].append(L[0])
                    else:
                        self.header[GLOBVAR_UNITS].append("")

                for n in self.header[GLOBVAR]:
                    if n == "CYCLE":
                        have_cycle = 1
                    if n == "TIME":
                        have_time = 1
                    if n == "DT":
                        have_dt = 1
                    if n == "CPU":
                        have_cpu = 1

                if not have_cycle:
                    self.header[GLOBVAR].append("CYCLE")
                    self.header[GLOBVAR_UNITS].append("")
                if not have_time:
                    self.header[GLOBVAR].append("TIME")
                    self.header[GLOBVAR_UNITS].append("S")
                if not have_dt:
                    self.header[GLOBVAR].append("DT")
                    self.header[GLOBVAR_UNITS].append("S")
                if not have_cpu:
                    self.header[GLOBVAR].append("CPU")
                    self.header[GLOBVAR_UNITS].append("S")

                idpts = array.array("i")
                idpts.fromfile(fp, num_points)
                if swapbytes:
                    idpts.byteswap()

                idmat = array.array("i")
                idmat.fromfile(fp, num_mats)
                if swapbytes:
                    idmat.byteswap()

                itype = array.array("i")
                itype.fromfile(fp, num_points)
                if swapbytes:
                    itype.byteswap()

                for i in range(num_points):
                    self.header[POINTID].append((idpts[i], itype[i]))
                for i in range(num_mats):
                    self.header[MATID].append(idmat[i])

                got_var_names = 1

            elif icode < 0:
                fp.close()
                raise IOError(
                    "*** error: unknown code:" + str(icode) + " (corrupt file?)"
                )

            else:
                if not got_counts:
                    fp.close()
                    raise IOError(
                        "*** error: variable values cannot come "
                        + "before variable counts (corrupt file?)"
                    )

                # read a dump of the variable values; icode is the dump number

                self._remove_repeats(icode)
                self.cycles.append(icode)
                self.times.append(ra[0])
                self.timesteps.append(ra[1])
                self.cputimes.append(ra[2])

                newvals = []
                for i in range(num_points):
                    a = array.array("f")
                    a.fromfile(fp, num_point_vars)
                    if swapbytes:
                        a.byteswap()
                    newvals.append(a.tolist())
                self.point_values.append(newvals)

                newvals = []
                for i in range(num_mats):
                    a = array.array("f")
                    a.fromfile(fp, num_mat_vars)
                    if swapbytes:
                        a.byteswap()
                    newvals.append(a.tolist())
                self.mat_values.append(newvals)

                a = array.array("f")
                a.fromfile(fp, num_glob_vars)
                if swapbytes:
                    a.byteswap()
                L = a.tolist()
                if not have_cycle:
                    L.append(self.cycles[-1])
                if not have_time:
                    L.append(self.times[-1])
                if not have_dt:
                    L.append(self.timesteps[-1])
                if not have_cpu:
                    L.append(self.cputimes[-1])
                self.glob_values.append(L)

                num_dumps = num_dumps + 1

            # read past the padding on the end of a fortran record
            fp.read(paddingsize)

        fp.close()

        if got_counts and not got_var_names:
            raise IOError(
                "*** error: got variable counts but not the "
                + "variable names (corrupt file?)"
            )

        # determine variable groupings by using heuristic rules
        for h in [POINTVAR, MATVAR, GLOBVAR]:
            process_groups(
                self.header[h], self.groups[h], self.combined[h], self.group_xlist[h]
            )
            for gname, compL in list(self.groups[h].items()):
                iL = []
                for comp_name in compL:
                    iL.append(self.get_name_index(h, comp_name))
                self.group_indexes[h][gname] = iL

        return ""

    def _remove_repeats(self, newcycle):
        popcount = 0
        if self.nodups:
            i = -1
            while len(self.cycles) > 0 and newcycle <= self.cycles[i]:
                popcount = popcount + 1
                i = i - 1
        if popcount > 0:
            for i in range(popcount):
                self.cycles.pop(-1)
                self.times.pop(-1)
                self.timesteps.pop(-1)
                self.cputimes.pop(-1)
                self.point_values.pop(-1)
                self.mat_values.pop(-1)
                self.glob_values.pop(-1)


def process_groups(nameL, groupD, combinedL, xlistD):
    """
    For the list of names 'nameL', vector and tensor grouping is performed.  The
    'groupD' dictionary is used to store the group names:
    ``groupD[group_name] = [list of component names]``.
    The 'combinedL' list is filled with the group
    names plus each name in the 'nameL' list that is not a component of a group.
    The 'xlistD' parallels the 'groupD' dictionary (same keys) and contains a

    list of the component extension names for each group name.
    """
    cD = {}  # names that have been identified as components of a group
    for n in nameL:
        if n not in cD:
            g, cL, xL = group_search(n, nameL)
            if g is not None:
                groupD[g] = cL
                xlistD[g] = xL
                combinedL.append(g)
                for c in cL:
                    cD[c] = None

    for n in nameL:
        if n not in cD:
            combinedL.append(n)


def group_search(n, nameL):
    """
    Search for a group using the given name 'n' as the first component.
    If all remaining components of a known group exist in the 'nameL' name
    list, the group name and a list of the component names is returned.
    If a group is not found, then (None, None) is returned.

    """
    i = len(n) - 1
    while i >= 0 and n[i] in " -_":
        i = i - 1

    cL = []
    xL = []

    def pre_check(*args):
        del cL[:]
        del xL[:]
        for c in args:
            n2 = c + n[len(c) :]
            n3 = byte_string.lower(c) + n[len(c) :]
            if n2 in nameL:
                cL.append(n2)
                xL.append(c)
            elif n3 in nameL:
                cL.append(n3)
                xL.append(c)
            else:
                return 0
        return 1

    def post_check(idx, *args):
        del cL[:]
        del xL[:]
        for c in args:
            n2 = n[:idx] + c + n[idx + len(c) :]
            n3 = n[:idx] + byte_string.lower(c) + n[idx + len(c) :]
            if n2 in nameL:
                cL.append(n2)
                xL.append(c)
            elif n3 in nameL:
                cL.append(n3)
                xL.append(c)
            else:
                return 0
        return 1

    if i >= 2 and byte_string.upper(n[i - 1 : i + 1]) == "XX":
        g = byte_string.rstrip(
            byte_string.rstrip(byte_string.rstrip(n[: i - 1]), "-"), "_"
        )
        if (
            post_check(i - 1, "XX", "YX", "ZX", "XY", "YY", "ZY", "XZ", "YZ", "ZZ")
            or post_check(i - 1, "XX", "YY", "ZZ", "XY", "YZ", "XZ")
            or post_check(i - 1, "XX", "YX", "XY", "YY", "ZZ")
            or post_check(i - 1, "XX", "YY", "ZZ", "XY")
            or post_check(i - 1, "YZ", "XZ", "XY")
        ):
            return g, cL, xL

    if i >= 1 and byte_string.upper(n[i]) == "X":
        g = byte_string.rstrip(byte_string.rstrip(byte_string.rstrip(n[:i]), "-"), "_")
        if post_check(i, "X", "Y", "Z") or post_check(i, "X", "Y"):
            return g, cL, xL

    if i >= 1 and byte_string.upper(n[i]) == "R":
        g = byte_string.rstrip(byte_string.rstrip(byte_string.rstrip(n[:i]), "-"), "_")
        if post_check(i, "R", "Z"):
            return g, cL, xL

    if i >= 1 and byte_string.upper(n[i]) == "S":
        g = byte_string.rstrip(byte_string.rstrip(byte_string.rstrip(n[:i]), "-"), "_")
        if post_check(i, "S", "X", "Y", "Z") or post_check(i, "S", "Z"):
            return g, cL, xL

    if len(n) > 1 and byte_string.upper(n[0]) == "X":
        g = byte_string.lstrip(byte_string.lstrip(byte_string.lstrip(n[1:]), "-"), "_")
        if pre_check("X", "Y", "Z") or pre_check("X", "Y"):
            return g, cL, xL

    return None, None, None


############################################################################


def echo_summary(fd):
    assert fd is not None

    tee.write("\n# hisdiff version", version, "summary\n")
    tee.write("# file name:", os.path.basename(fd.filename))

    timeL = fd.get_time_values()

    if len(timeL) > 0:
        minv = (timeL[0], 0)  # value, time index
        maxv = (timeL[0], 0)  # value, time index
        for k in range(len(timeL)):
            if minv[0] > timeL[k]:
                minv = (timeL[k], k)
            if maxv[0] < timeL[k]:
                maxv = (timeL[k], k)
        tee.write(
            "\nTIME STEPS absolute 1.e-15"
            + "\t # min "
            + str(minv[0])
            + " @ t"
            + str(minv[1])
            + "  max "
            + str(maxv[0])
            + " @ t"
            + str(maxv[1])
        )
    else:
        tee.write("\nTIME STEPS relative 1.e-6 floor 0.0")

    tee.write("\nPOINT VARIABLES relative 1.e-6 floor 0.0")

    nameL = fd.get_header_list(POINTVAR)
    idL = fd.get_header_list(POINTID)
    unitL = fd.get_units_list(POINTVAR)
    if len(nameL) > 0 and len(idL) > 0 and len(timeL) > 0:
        for i in range(len(nameL)):
            valsL = fd.get_values(POINTVAR, i, 0)
            assert len(valsL) == len(timeL)
            minv = (valsL[0], 0, 0)  # value, time index, id index
            maxv = (valsL[0], 0, 0)  # value, time index, id index
            for j in range(len(idL)):
                valsL = fd.get_values(POINTVAR, i, j)
                for k in range(len(valsL)):
                    if minv[0] > valsL[k]:
                        minv = (valsL[k], k, j)
                    if maxv[0] < valsL[k]:
                        maxv = (valsL[k], k, j)
            tee.write(
                "\t%-20s # %-10s min %8.1e @ t%-3d id%-3d : max %8.1e @ t%-3d id%-3d"
                % (
                    nameL[i],
                    "[" + unitL[i] + "]",
                    minv[0],
                    minv[1],
                    idL[minv[2]][0],
                    maxv[0],
                    maxv[1],
                    idL[maxv[2]][0],
                )
            )
    elif len(nameL) > 0:
        for n in nameL:
            tee.write("\t" + n)

    tee.write("\nMATERIAL VARIABLES relative 1.e-6 floor 0.0")

    nameL = fd.get_header_list(MATVAR)
    idL = fd.get_header_list(MATID)
    unitL = fd.get_units_list(MATVAR)
    if len(nameL) > 0 and len(idL) > 0 and len(timeL) > 0:
        for i in range(len(nameL)):
            valsL = fd.get_values(MATVAR, i, 0)
            assert len(valsL) == len(timeL)
            minv = (valsL[0], 0, 0)  # value, time index, id index
            maxv = (valsL[0], 0, 0)  # value, time index, id index
            for j in range(len(idL)):
                valsL = fd.get_values(MATVAR, i, j)
                for k in range(len(valsL)):
                    if minv[0] > valsL[k]:
                        minv = (valsL[k], k, j)
                    if maxv[0] < valsL[k]:
                        maxv = (valsL[k], k, j)
            tee.write(
                "\t%-20s # %-10s min %8.1e @ t%-3d id%-3d : max %8.1e @ t%-3d id%-3d"
                % (
                    nameL[i],
                    "[" + unitL[i] + "]",
                    minv[0],
                    minv[1],
                    idL[minv[2]],
                    maxv[0],
                    maxv[1],
                    idL[maxv[2]],
                )
            )
    elif len(nameL) > 0:
        for n in nameL:
            tee.write("\t" + n)

    tee.write("\nGLOBAL VARIABLES relative 1.e-6 floor 0.0")

    nameL = fd.get_header_list(GLOBVAR)
    unitL = fd.get_units_list(GLOBVAR)
    if len(nameL) > 0 and len(timeL) > 0:
        for i in range(len(nameL)):
            valsL = fd.get_values(GLOBVAR, i)
            assert len(valsL) == len(timeL)
            minv = (valsL[0], 0)  # value, time index
            maxv = (valsL[0], 0)  # value, time index
            for k in range(len(valsL)):
                if minv[0] > valsL[k]:
                    minv = (valsL[k], k)
                if maxv[0] < valsL[k]:
                    maxv = (valsL[k], k)
            tee.write(
                "\t%-20s # %-10s min %8.1e @ t%-3d : max %8.1e @ t%-3d"
                % (nameL[i], "[" + unitL[i] + "]", minv[0], minv[1], maxv[0], maxv[1])
            )
    elif len(nameL) > 0:
        for n in nameL:
            tee.write("\t" + n)


############################################################################


class ParseError(Exception):
    def __init__(self, msg=None):
        self.msg = "ParseError" + "" if msg is None else (": " + msg)
        super(ParseError, self).__init__(self.msg)

    def __str__(self):
        return self.msg


POINT_SPECS = 0
MATERIAL_SPECS = 1
GLOBAL_SPECS = 2


class TotalSpecs:
    def __init__(self):
        self.default_tol = Tolerance()
        self.times_tol = Tolerance()
        self.times_active = 1
        self.times_overlap = 0  # true means only compare overlapping times
        self.times_interpolate = 0
        self.specs = [VarSpecs("Point"), VarSpecs("Material"), VarSpecs("Global")]

    def set_overlap_times(self, on_off):
        if on_off:
            self.times_overlap = 1
        else:
            self.times_overlap = 0

    def set_interpolate_times(self, on_off):
        if on_off:
            self.times_interpolate = 1
        else:
            self.times_interpolate = 0

    def inactivate(self):
        """
        Each variable type is set to inactive.
        """
        self.times_active = 0
        self.specs[0].active = 0
        self.specs[1].active = 0
        self.specs[2].active = 0

    def activate(self, spectype):
        self.specs[spectype].active = 1

    def overlapping_times(self):
        return self.times_overlap

    def interpolate_times(self):
        return self.times_interpolate

    def get_specs(self, spectype):
        assert spectype >= POINT_SPECS and spectype <= GLOBAL_SPECS
        return self.specs[spectype]

    def get_total_default(self):
        return self.default_tol

    def get_times_tolerance(self):
        return self.times_tol

    def get_default(self, spectype):
        assert spectype >= POINT_SPECS and spectype <= GLOBAL_SPECS
        return self.specs[spectype].get_default()

    def exclude(self, spectype, varL):
        """
        Any variable names that are to be excluded are subtracted from the
        varL list and all remaining returned in a new list.
        """
        assert spectype >= POINT_SPECS and spectype <= GLOBAL_SPECS
        L = []
        if self.specs[spectype].active:
            nl = 0
            nx = 0
            for v in varL:
                p = self.specs[spectype].get_var(v)
                if p is not None:
                    if p[0]:
                        nx = nx + 1
                    else:
                        nl = nl + 1
            all = self.specs[spectype].all
            for v in varL:
                p = self.specs[spectype].get_var(v)
                if p is None:
                    if all or nl == 0 or nx > 0:
                        L.append(v)
                elif not p[0]:
                    L.append(v)
        return L

    def output(self, fp, point_ext, mat_ext, glob_ext):
        fp.write("Global default tol: " + self.default_tol.to_string() + "\n")
        if self.times_interpolate:
            fp.write(
                "Interpolation is taking place and time step tol is not needed "
                "and difference in time are taken into account.\n"
            )
        else:
            fp.write("Time step tol: " + self.times_tol.to_string() + "\n")
        fp.write("Point Specifications:\n")
        self.specs[POINT_SPECS].output(fp, point_ext)
        fp.write("Material Specifications:\n")
        self.specs[MATERIAL_SPECS].output(fp, mat_ext)
        fp.write("Global Specifications:\n")
        self.specs[GLOBAL_SPECS].output(fp, glob_ext)


class VarSpecs:
    def __init__(self, spectypename):
        self.spectypename = spectypename
        self.active = 1  # false if this spec type is not to be compared
        self.tol = Tolerance()
        self.all = 0
        self.name_specs = {}  # maps name to (bool,tol) where bool is true if
        # the variable is to be excluded (a ! char was
        # used) and tol is a Tolerance object

    def get_default(self):
        return self.tol

    def set_all(self):
        self.all = 1

    def add_name_spec(self, name, exclude, tol):
        self.name_specs[name] = (exclude, tol)

    def get_var(self, name):
        return self.name_specs.get(name, None)

    def get_tol(self, name):
        return self.name_specs[name][1]

    def get_var_names(self):
        L = []
        if self.active:
            for n, p in list(self.name_specs.items()):
                x = p[0]
                if not x:
                    L.append(n)
        return L

    def load_var_names(self, varnames, groupD, addnames):
        """
        'varnames' is the raw variable names in the file (components)
        'groupD' is a dictionary of the groups mapped to the components
        'addnames' all possible names to be added (if needed)
        """
        if self.active:
            newD = {}

            if len(self.name_specs) > 0:  # at least one variable specified
                num_excluded = 0
                num_listed = 0
                for n, p in list(self.name_specs.items()):
                    x = p[0]
                    t = p[1]
                    if x:
                        num_excluded = num_excluded + 1
                    else:
                        num_listed = num_listed + 1
                        if n in varnames or n in groupD:
                            newD[n] = (x, t)

                all = self.all
                if num_excluded > 0 and num_listed > 0 and not self.all:
                    tee.write(
                        "hisdiff: NOTE: input file specifications for",
                        self.spectypename,
                        "variables contain both excluded and",
                        "non-excluded names without using the ALL keyword;",
                        "assuming ALL",
                    )
                    all = 1

                if all or num_listed == 0:
                    # add any variables that were not already specified
                    for n in addnames:
                        if n not in self.name_specs:
                            if n in groupD:
                                addL = [n]
                                for c1 in groupD[n]:
                                    if c1 in self.name_specs:
                                        # a component of this group was listed
                                        # in the input, so only add the
                                        # components that were not listed
                                        del addL[:]
                                        for c2 in groupD[n]:
                                            if c2 not in self.name_specs:
                                                addL.append(c2)
                                        break
                                for c1 in addL:
                                    newD[c1] = (0, self.tol)
                            else:
                                newD[n] = (0, self.tol)
                elif num_excluded == 0:
                    # variables were listed and none excluded, so explicitely set
                    # the other variables as excluded
                    for n in varnames + list(groupD.keys()):
                        if n not in self.name_specs:
                            newD[n] = (1, self.tol)

            else:  # no variables were listed, so add all of them
                for n in addnames:
                    newD[n] = (0, self.tol)

            self.name_specs = newD

    def output(self, fp, group_ext):
        L = list(self.name_specs.items())
        L.sort()
        first = 1
        for n, p in L:
            x = p[0]
            t = p[1]
            if not x:
                if not first:
                    fp.write(os.linesep)
                nx = n
                L = group_ext.get(n, None)
                if L is not None:
                    nx = nx + " [" + byte_string.join(L, ",") + "]"
                fp.write(" %-30s" % nx)
                fp.write(" " + t.to_string())
                first = 0
        fp.write(os.linesep)


class Tolerance:
    def __init__(self):
        self.diff = "rel"
        self.tol = 1.0e-6
        self.floor = 0.0
        self.norm = "Linf"

    def copy(self, x):
        self.diff = x.diff
        self.tol = x.tol
        self.floor = x.floor
        self.norm = x.norm

    def set_tolerance(self, diff, tol):
        assert diff in ["rel", "abs"]
        self.diff = diff
        self.tol = tol

    def set_floor(self, floor):
        self.floor = floor

    def set_norm(self, norm):
        self.norm = norm

    def difference(self, v1, v2):
        if self.diff == "abs":
            return float(abs(v2 - v1))
        if abs(v1) < self.floor and abs(v2) < self.floor:
            return 0.0
        if v1 == 0.0 and v2 == 0.0:
            return 0.0
        return float(abs(v2 - v1)) / float(max(abs(v1), abs(v2)))

    def to_string(self):
        s = byte_string.upper(self.diff) + " %-8g" % self.tol
        s = s + " FLR %-8g" % self.floor + "  NORM " + self.norm
        return s

    def apply_norm(self, vals1, vals2, timeL, deltL):
        """
        Dispatches to the norm defined in this object.  The 'vals1' and 'vals2'
        lists must have a length the same as 'timeL' or an integer multiple.
        For example, len(vals1) == 3*len(timeL) when processing 3D velocity as
        a group.
        """
        rslt_str = None
        if self.norm == "Ind":
            rslt_str = apply_ind_point(timeL, vals1, vals2, self)
        else:
            if self.norm == "L1":
                absnrm, nrm, max1, max2 = apply_l1(
                    vals1, vals2, deltL, self.diff, self.floor
                )
            elif self.norm == "L2":
                absnrm, nrm, max1, max2 = apply_l2(
                    vals1, vals2, deltL, self.diff, self.floor
                )
            else:
                assert self.norm == "Linf"
                absnrm, nrm, max1, max2 = apply_linf(
                    vals1, vals2, deltL, self.diff, self.floor
                )
            if nrm > self.tol:
                if self.diff == "rel":
                    rslt_str = (
                        " %-4s(x) %15.8e, %-4s(y) %15.8e, "
                        + "%-4s(x-y) %15.8e, rel diff = %10.3e (FAILED)"
                    ) % (self.norm, max1, self.norm, max2, self.norm, absnrm, nrm)
                else:
                    assert self.diff == "abs"
                    rslt_str = (
                        " %-4s(x) %15.8e, %-4s(y) %15.8e, "
                        + "%-4s(x-y) = %10.3e (FAILED)"
                    ) % (self.norm, max1, self.norm, max2, self.norm, nrm)

        return rslt_str

    def apply_prof_norm(self, vals1, vals2, x1, x2):
        """
        Dispatches to the norm defined in this object.  The 'vals1' and 'vals2'
        lists must have a length the same as 'timeL' or an integer multiple.
        For example, len(vals1) == 3*len(timeL) when processing 3D velocity as
        a group.
        """
        rslt_str = None

        # Check monotonicity
        for i in range(len(x1) - 1):
            if x1[i + 1] >= x1[i]:
                continue
            else:
                sys.stderr.write(
                    "*** error: x1 data must be strictly "
                    + "monotonically increasing for this algorithm\n"
                )
                return 1

        # Now examine data and compute norm
        #  Could add better checking of domain overlap
        ns1, ne1, ns2 = get_domain_overlap(x1, x2)
        # use functions like profile norm
        if self.norm == "L2":
            norm_y1, norm_y2, norm_dy = L2_on_x1(x1, vals1, x2, vals2, (ns1, ne1, ns2))
        elif self.norm == "L1":
            norm_y1, norm_y2, norm_dy = L1_on_x1(x1, vals1, x2, vals2, (ns1, ne1, ns2))
        elif self.norm == "Linf":
            norm_y1, norm_y2, norm_dy = Linf_on_x1(
                x1, vals1, x2, vals2, (ns1, ne1, ns2)
            )

        Ndif = norm_dy

        if norm_y1 < self.floor and norm_y2 < self.floor:
            nrm = 0.0
        elif self.diff == "rel":
            if norm_y1 == 0.0 and norm_y2 == 0.0:
                nrm = 0.0
            else:
                nrm = norm_dy / max(norm_y2, norm_y1)
        else:
            assert self.diff == "abs"
            nrm = Ndif

        if nrm > self.tol:
            if self.diff == "rel":
                rslt_str = (
                    " %-4s(x) %15.8e, %-4s(y) %15.8e, "
                    + "%-4s(x-y) %15.8e, rel diff = %10.3e (FAILED)"
                ) % (
                    self.norm,
                    norm_y1,
                    self.norm,
                    norm_y2,
                    self.norm,
                    norm_dy,
                    norm_dy / max(norm_y2, norm_y1),
                )
            else:
                assert self.diff == "abs"
                rslt_str = (
                    " %-4s(x) %15.8e, %-4s(y) %15.8e, " + "%-4s(x-y) = %10.3e (FAILED)"
                ) % (self.norm, norm_y1, self.norm, norm_y2, self.norm, norm_dy)

        return rslt_str


def match(s, key, n=None):
    """
    Returns true if the string 's' is equal to 'key'.  Abbreviations to 'key'
    are allowed but must be at least 'n' characters.  Case is ignored.
    """
    if n is None:
        return byte_string.upper(s) == byte_string.upper(key)
    assert len(key) >= n
    l = len(s)  # noqa
    if l < n or l > len(key):
        return 0
    return byte_string.upper(s) == byte_string.upper(key)[:l]


def parse_tol(tokL, toki, lineno, tol):
    while toki < len(tokL):
        if tokL[toki][:1] == "#":
            break

        if match(tokL[toki], "RELATIVE", 3) or match(tokL[toki], "ABSOLUTE", 3):
            d = byte_string.lower(tokL[toki])[:3]
            if toki == len(tokL) - 1 or tokL[toki + 1][:1] == "#":
                raise ParseError(
                    'expected a number after "'
                    + tokL[toki]
                    + '" (at line '
                    + str(lineno)
                    + ")"
                )
            toki = toki + 1
            try:
                t = float(tokL[toki])
            except:  # noqa
                raise ParseError(
                    'failed to parse number "'
                    + tokL[toki]
                    + '" (at line '
                    + str(lineno)
                    + ")"
                )
            tol.set_tolerance(d, t)

        elif match(tokL[toki], "FLOOR", 3):
            if toki == len(tokL) - 1 or tokL[toki + 1][:1] == "#":
                raise ParseError(
                    'expected a number after "'
                    + tokL[toki]
                    + '" (at line '
                    + str(lineno)
                    + ")"
                )
            toki = toki + 1
            try:
                t = float(tokL[toki])
            except:  # noqa
                raise ParseError(
                    'failed to parse number "'
                    + tokL[toki]
                    + '" (at line '
                    + str(lineno)
                    + ")"
                )
            tol.set_floor(t)

        elif match(tokL[toki], "INDIVIDUAL", 3):
            tol.set_norm("Ind")

        elif match(tokL[toki], "L1"):
            tol.set_norm("L1")

        elif match(tokL[toki], "L2"):
            tol.set_norm("L2")

        elif match(tokL[toki], "LINF"):
            tol.set_norm("Linf")

        else:
            raise ParseError(
                'unexpected token "' + tokL[toki] + '" (at line ' + str(lineno) + ")"
            )
        toki = toki + 1


def parse_command_file(specs, filename):
    """ """
    specs.inactivate()

    fp = open(filename, "r")
    lineL = fp.readlines()
    fp.close()

    lineno = 1
    while lineno <= len(lineL):
        line = lineL[lineno - 1]
        s = byte_string.strip(line)
        if len(s) > 0 and s[0] != "#":
            L = byte_string.split(s)
            assert len(L) > 0

            if len(L) == 1:
                raise ParseError("unknown keyword at line " + str(lineno) + ": " + s)
            else:
                if match(L[0], "DEFAULT", 3) and match(L[1], "TOLERANCE", 3):
                    parse_tol(L, 2, lineno, specs.get_total_default())
                    specs.get_times_tolerance().copy(specs.get_total_default())
                    specs.get_default(POINT_SPECS).copy(specs.get_total_default())
                    specs.get_default(MATERIAL_SPECS).copy(specs.get_total_default())
                    specs.get_default(GLOBAL_SPECS).copy(specs.get_total_default())
                elif match(L[0], "IGNORE", 3) and match(L[1], "CASE", 3):
                    pass  # case is always ignored
                elif match(L[0], "STEP", 3) and match(L[1], "OFFSET", 3):
                    pass  # not implemented
                elif match(L[0], "TIME", 3) and match(L[1], "STEPS", 3):
                    specs.times_active = 1
                    parse_tol(L, 2, lineno, specs.get_times_tolerance())
                elif match(L[0], "RETURN", 3) and match(L[1], "STATUS", 3):
                    pass  # not implemented
                elif match(L[0], "POINT", 3) and match(L[1], "VARIABLES", 3):
                    specs.activate(POINT_SPECS)
                    lineno = parse_variables(
                        lineno, lineL, specs.get_specs(POINT_SPECS)
                    )
                elif match(L[0], "MATERIAL", 3) and match(L[1], "VARIABLES", 3):
                    specs.activate(MATERIAL_SPECS)
                    lineno = parse_variables(
                        lineno, lineL, specs.get_specs(MATERIAL_SPECS)
                    )
                elif match(L[0], "GLOBAL", 3) and match(L[1], "VARIABLES", 3):
                    specs.activate(GLOBAL_SPECS)
                    lineno = parse_variables(
                        lineno, lineL, specs.get_specs(GLOBAL_SPECS)
                    )
                else:
                    raise ParseError(
                        "unknown keyword at line " + str(lineno) + ": " + s
                    )

        lineno = lineno + 1


def parse_variables(lineno, lineL, specs):
    assert lineno <= len(lineL)
    L = byte_string.split(lineL[lineno - 1])
    if len(L) > 2 and L[2][:1] != "#":
        if match(L[2], "ALL") or match(L[2], "(ALL)"):
            specs.set_all()
            parse_tol(L, 3, lineno, specs.get_default())
        else:
            parse_tol(L, 2, lineno, specs.get_default())
    lineno = lineno + 1

    while lineno <= len(lineL):
        line = lineL[lineno - 1]
        s = byte_string.strip(line)
        if len(s) == 0:
            break
        if s[0] == "#":
            pass  # comments are ignored
        elif line[0] == "\t":
            L = byte_string.split(s)
            vname = L[0]
            exclude = 0
            if vname[0] == "!":
                exclude = 1
                vname = vname[1:]
            tol = Tolerance()
            tol.copy(specs.get_default())
            if len(L) > 1 and L[1][0] != "#":
                parse_tol(L, 1, lineno, tol)
            specs.add_name_spec(vname, exclude, tol)
        else:
            break

        lineno = lineno + 1

    return lineno


############################################################################


def varwarn(specs, spectype, hdrtype, f1, f2, nosymm):
    if spectype == POINT_SPECS:
        s = "point"
    elif spectype == MATERIAL_SPECS:
        s = "material"
    else:
        s = "global"
    L1 = specs.exclude(spectype, f1.get_header_list(hdrtype))
    L2 = specs.exclude(spectype, f2.get_header_list(hdrtype))
    for n in L1:
        if n not in L2:
            tee.write(
                "hisdiff: WARNING:",
                s,
                "variable",
                n,
                "contained in first file but not the second",
            )
    if not nosymm:
        for n in L2:
            if n not in L1:
                tee.write(
                    "hisdiff: WARNING:",
                    s,
                    "variable",
                    n,
                    "contained in second file but not the first",
                )

    L1 = f1.get_header_list(hdrtype)
    L2 = f2.get_header_list(hdrtype)
    G1 = f1.get_group_dict(hdrtype)
    G2 = f2.get_group_dict(hdrtype)
    for n in specs.get_specs(spectype).get_var_names():
        if (n not in L1) and (n not in L2) and (n not in G1) and (n not in G2):
            tee.write(
                "hisdiff: WARNING:",
                s,
                "variable",
                n,
                "specified in command file but it is not in either history file",
            )


def intersect_lists(L1, L2):
    L = []
    for n in L1:
        if n in L2:
            L.append(n)
    return L


def varload(specs, spectype, hdrtype, f1, f2):
    """
    intersect the var names in each file
    """
    varnames = intersect_lists(f1.get_header_list(hdrtype), f2.get_header_list(hdrtype))
    addnames = intersect_lists(
        f1.get_header_combined_list(hdrtype), f2.get_header_combined_list(hdrtype)
    )
    grpD = {}
    G2 = f2.get_group_dict(hdrtype)
    for n, l in list(f1.get_group_dict(hdrtype).items()):
        if n in G2:
            grpD[n] = l
    specs.get_specs(spectype).load_var_names(varnames, grpD, addnames)


############################################################################


class IndexLists:
    def __init__(self):
        self.times1 = []  # list of time indexes for file1
        self.times2 = []  # list of time indexes for file2
        self.timetol = None  # time value Tolerance
        self.pointids = []  # list of (point id, index file1, index file 2)
        self.pointvars = []  # list of 4-tuples
        # (varname, index file 1, index file 2, Tolerance)
        self.matids = []  # list of (mat id, index file1, index file 2)
        self.matvars = []  # list of 4-tuples
        # (varname, index file 1, index file 2, Tolerance)
        self.globvars = []  # list of 4-tuples
        # (varname, index file 1, index file 2, Tolerance)

    def build_lists(self, specs, f1, f2):
        diff = 0

        L1 = f1.get_time_values()
        L2 = f2.get_time_values()

        if specs.times_active:
            self.timetol = specs.get_times_tolerance()

        if specs.overlapping_times():
            if len(L1) == 1 and len(L2) == 1:
                # special case of one time value each; if times are being compared
                # then assume they overlap, otherwise pick an arbitrary time scale
                if self.timetol is not None or abs(L1[0] - L2[0]) < 1.0e-6:
                    self.times1.append(0)
                    self.times2.append(0)
            elif len(L1) > 0 and len(L2) > 0:
                # if times are not being compared, compute a time scale based on
                # the maximum difference between any successive times
                scale = 0.0
                if self.timetol is None:
                    for i in range(len(L1) - 1):
                        if abs(L1[i] - L1[i + 1]) > scale:
                            scale = abs(L1[i] - L1[i + 1])
                    for i in range(len(L2) - 1):
                        if abs(L2[i] - L2[i + 1]) > scale:
                            scale = abs(L2[i] - L2[i + 1])
                # func to compute the index offset of 't' into a list 'L' of
                # ascending times; 't' must be >= the first value in 'L'

                def getoffset(t, L, ttol, d):
                    for i in range(len(L)):
                        if L[i] > t:
                            if i > 0 and abs(t - L[i - 1]) < abs(L[i] - t):
                                return i - 1
                            return i
                    # 't' is off the end; if times are being compared, assume the
                    # last value overlaps; otherwise, use 'scale' for a comparison
                    if ttol is not None:
                        return len(L) - 1
                    if abs(t - L[-1]) < 1.0e-6 * d:
                        return len(L) - 1
                    return len(L)

                if L1[0] < L2[0]:
                    i1 = getoffset(L2[0], L1, self.timetol, scale)
                    i2 = 0
                else:
                    i1 = 0
                    i2 = getoffset(L1[0], L2, self.timetol, scale)
                # walk the lists until one of them runs out of entries
                while i1 < len(L1) and i2 < len(L2):
                    self.times1.append(i1)
                    self.times2.append(i2)
                    i1 = i1 + 1
                    i2 = i2 + 1
        else:
            ntimes = min(len(L1), len(L2))
            if len(L1) != len(L2):
                if not specs.interpolate_times():
                    tee.write(
                        "hisdiff: files have different number of times ("
                        + "comparing the first "
                        + str(ntimes)
                        + ")"
                    )
                    diff = 1
            for i in range(ntimes):
                self.times1.append(i)
                self.times2.append(i)

        pspecs = specs.get_specs(POINT_SPECS)
        if pspecs.active:
            # ignore the tracer types (lagrangian, ale, eulerian)
            L1 = [T[0] for T in f1.get_header_list(POINTID)]
            L2 = [T[0] for T in f2.get_header_list(POINTID)]
            for i1 in range(len(L1)):
                try:
                    i2 = L2.index(L1[i1])
                    self.pointids.append((L1[i1], i1, i2))
                except ValueError:
                    tee.write(
                        "hisdiff: Point id",
                        L1[i1],
                        "is in the first file but not the second (it will be ignored)",
                    )
                    diff = 1
            for n in pspecs.get_var_names():
                i1 = f1.get_name_index(POINTVAR, n)
                i2 = f2.get_name_index(POINTVAR, n)
                assert i1 is not None and i2 is not None
                self.pointvars.append((n, i1, i2, pspecs.get_tol(n)))

        mspecs = specs.get_specs(MATERIAL_SPECS)
        if mspecs.active:
            L1 = f1.get_header_list(MATID)
            L2 = f2.get_header_list(MATID)
            for i1 in range(len(L1)):
                try:
                    i2 = L2.index(L1[i1])
                    self.matids.append((L1[i1], i1, i2))
                except ValueError:
                    tee.write(
                        "hisdiff: Material id",
                        L1[i1],
                        "is in the first file but not the second (it will be ignored)",
                    )
                    diff = 1
            for n in mspecs.get_var_names():
                i1 = f1.get_name_index(MATVAR, n)
                i2 = f2.get_name_index(MATVAR, n)
                assert i1 is not None and i2 is not None
                self.matvars.append((n, i1, i2, mspecs.get_tol(n)))

        gspecs = specs.get_specs(GLOBAL_SPECS)
        if gspecs.active:
            for n in gspecs.get_var_names():
                i1 = f1.get_name_index(GLOBVAR, n)
                i2 = f2.get_name_index(GLOBVAR, n)
                assert i1 is not None and i2 is not None
                self.globvars.append((n, i1, i2, gspecs.get_tol(n)))

        return diff


############################################################################


def apply_ind_point(timeL, L1, L2, tol):
    """ """
    rslt_str = ""
    maxd = 0.0
    maxv1 = None
    maxv2 = None
    maxt = None
    for i in range(len(L1)):
        if abs(L1[i]) < tol.floor and abs(L2[i]) < tol.floor:
            d = 0.0
        elif tol.diff == "abs":
            d = abs(L2[i] - L1[i])
        elif L1[i] == 0.0 and L2[i] == 0.0:
            d = 0.0
        else:
            d = abs(L2[i] - L1[i]) / max(abs(L1[i]), abs(L2[i]))

        if d > maxd:
            maxd = d
            maxv1 = L1[i]
            maxv2 = L2[i]
            maxt = timeL[i % len(timeL)]

    if maxd > tol.tol:
        rslt_str = (
            " at time %15.8e, values %15.8e & %15.8e, " + "%s diff = %10.3e (FAILED)"
        ) % (maxt, maxv1, maxv2, tol.diff, maxd)

    return rslt_str


def apply_l1(vals1, vals2, deltL, relabs, floor):
    """ """
    Ndif = 0.0
    NL1 = 0.0
    NL2 = 0.0
    for i1 in range(len(vals1)):
        dt = deltL[i1 % len(deltL)]
        Ndif += abs(vals2[i1] - vals1[i1]) * dt
        NL1 += abs(vals1[i1]) * dt
        NL2 += abs(vals2[i1]) * dt
    if NL1 < floor and NL2 < floor:
        Norm = 0.0
    elif relabs == "rel":
        if NL1 == 0.0 and NL2 == 0.0:
            Norm = 0.0
        else:
            Norm = Ndif / max(NL1, NL2)
    else:
        assert relabs == "abs"
        Norm = Ndif
    return [Ndif, Norm, NL1, NL2]


def apply_l2(vals1, vals2, deltL, relabs, floor):
    """ """
    dif = 0.0
    NL1 = 0.0
    NL2 = 0.0
    for i1 in range(len(vals1)):
        dt = deltL[i1 % len(deltL)]
        dif += ((vals2[i1] - vals1[i1]) ** 2.0) * dt
        NL1 += (vals1[i1] ** 2.0) * dt
        NL2 += (vals2[i1] ** 2.0) * dt
    Ndif = sqrt(dif)
    NL1 = sqrt(NL1)
    NL2 = sqrt(NL2)
    if NL1 < floor and NL2 < floor:
        Norm = 0.0
    elif relabs == "rel":
        if NL1 == 0.0 and NL2 == 0.0:
            Norm = 0.0
        else:
            Norm = Ndif / max(NL1, NL2)
    else:
        assert relabs == "abs"
        Norm = Ndif
    return [Ndif, Norm, NL1, NL2]


def apply_linf(vals1, vals2, deltL, relabs, floor):
    """ """
    Maxdif = 0.0
    Max_L1 = 0.0
    Max_L2 = 0.0
    for i1 in range(len(vals1)):
        Maxdif = max(abs(vals2[i1] - vals1[i1]), Maxdif)
        Max_L1 = max(abs(vals1[i1]), Max_L1)
        Max_L2 = max(abs(vals2[i1]), Max_L2)
    if Max_L1 < floor and Max_L2 < floor:
        Norm = 0.0
    elif relabs == "rel":
        if Max_L1 == 0.0 and Max_L2 == 0.0:
            Norm = 0.0
        else:
            Norm = Maxdif / (max(Max_L1, Max_L2))
    else:
        assert relabs == "abs"
        Norm = Maxdif
    return [Maxdif, Norm, Max_L1, Max_L2]


############################################################################
# Here we have our functions for apply_prof_norm


def get_left_index(x, xvec, nl):
    if xvec[nl] == x:  # Check for this separately; this avoids
        #  accessing xvec[nl+1] if not necessary.
        return nl
    if (xvec[nl] < x) and (x < xvec[nl + 1]):
        return nl
    else:
        return get_left_index(x, xvec, nl + 1)


def get_domain_overlap(x1, x2):
    """Find the domain shared by x1 and x2. This assumes data on x2
    will be interpolated onto x1, which leads to some asymmetry in the
    index calculations.

    ns1: index of x1 at the start of the overlap
    ne1: index of x1 at the end of the overlap
    ns2: index of x2 at the start of the overlap

    xs = x1[ns1]
    xe = x1[ne1]

    Return xs, xe, ns1, ne1, ns2
    """
    ns1 = 0
    ne1 = len(x1) - 1
    # Find the beginning of the overlap
    if x1[0] <= x2[0]:
        ns2 = 0
        for i in range(len(x1)):
            if x1[i] >= x2[ns2]:
                ns1 = i
                break
    else:
        for i in range(1, len(x2)):
            if x2[i] >= x1[0]:
                ns2 = i - 1
                break

    # Find the end of the overlap
    if x1[-1] > x2[-1]:
        for i in range(ns1, len(x1)):
            if x1[i] > x2[-1]:
                ne1 = i - 1
                break
            if x1[i] == x2[-1]:
                ne1 = i
                break

    return ns1, ne1, ns2


def L2_on_x1(x1, y1, x2, y2, indices=None):
    """Compute the L2 norm of y1, y2, and y2-y1 on an overlap
    region.

    L2_y1 = abs(y1_0)^2*dx_0 + abs(y1_1)^2*dx_1 + ... + abs(y1_i)^2*dx_i
    L2_y2 = abs(y2_0)^2*dx_0 + abs(y2_1)^2*dx_1 + ... + abs(y2_i)^2*dx_i
    L2_dy = abs(dy_0)^2*dx_0 + abs(dy_1)^2*dx_1 + ... + abs(dy_i)^2*dx_i
    dy = y1-y2_interp

    The overlap region is the common domain between x1 and x2. Before
    computing the norms, y2 data is interpolated onto x1. The norms
    are weighted by the spacing between the points in x1. Since data
    is always evaluated on x1, the ordering of the input arguments is
    important.

    indices is a tuple containing the results of
    get_domain_overlap(x1, x2)

    Return L2 norms of y1, y2, and (y2-y1)
    """
    # ns1, ne1, and ns2 are the start and end indices of the overlap on x1,
    # and the start index of the overlap on x2
    if indices is None:
        ns1, ne1, ns2 = get_domain_overlap(x1, x2)
    else:
        (ns1, ne1, ns2) = indices

    j = ns2

    dx1_sum = 0.0
    y1_sq_sum = 0.0
    y2_sq_sum = 0.0
    dy_sq_sum = 0.0

    dx1_left = 0.0
    for i in range(ns1, ne1):
        j = get_left_index(x1[i], x2, j)

        slope = (y2[j + 1] - y2[j]) / (x2[j + 1] - x2[j])
        y2_interp = y2[j] + slope * (x1[i] - x2[j])

        dx1_right = 0.5 * (x1[i + 1] - x1[i])
        dx1 = dx1_left + dx1_right

        y1_sq_sum = y1_sq_sum + dx1 * (y1[i]) ** 2
        y2_sq_sum = y2_sq_sum + dx1 * (y2_interp) ** 2
        dy_sq_sum = dy_sq_sum + dx1 * (y1[i] - y2_interp) ** 2
        dx1_sum = dx1_sum + dx1

        # for next iteration
        dx1_left = dx1_right

    # Last interval
    i = ne1
    j = get_left_index(x1[i], x2, j)

    if x1[i] == x2[j]:
        y2_interp = y2[j]
    else:
        slope = (y2[j + 1] - y2[j]) / (x2[j + 1] - x2[j])
        y2_interp = y2[j] + slope * (x1[i] - x2[j])

    dx1 = dx1_left

    y1_sq_sum = y1_sq_sum + dx1 * (y1[i]) ** 2
    y2_sq_sum = y2_sq_sum + dx1 * (y2_interp) ** 2
    dy_sq_sum = dy_sq_sum + dx1 * (y1[i] - y2_interp) ** 2
    dx1_sum = dx1_sum + dx1

    # Done with last interval

    L2_y1 = sqrt(y1_sq_sum)  # /dx1_sum)
    L2_y2 = sqrt(y2_sq_sum)  # /dx1_sum)
    L2_dy = sqrt(dy_sq_sum)  # /dx1_sum)

    return L2_y1, L2_y2, L2_dy


def L1_on_x1(x1, y1, x2, y2, indices=None):
    """Compute the L1 norm of y1, y2, and y2-y1 on an overlap
    region.

    L1_y1 = abs(y1_0)*dx_0 + abs(y1_1)*dx_1 + ... + abs(y1_i)*dx_i
    L1_y2 = abs(y2_0)*dx_0 + abs(y2_1)*dx_1 + ... + abs(y2_i)*dx_i
    L1_dy = abs(dy_0)*dx_0 + abs(dy_1)*dx_1 + ... + abs(dy_i)*dx_i
    dy = y1-y2_interp

    The overlap region is the common domain between x1 and x2. Before
    computing the norms, y2 data is interpolated onto x1. The norms
    are weighted by the spacing between the points in x1. Since data
    is always evaluated on x1, the ordering of the input arguments is
    important.

    indices is a tuple containing the results of
    get_domain_overlap(x1, x2)

    Return L1 norms of y1, y2, and (y2-y1)
    """

    # ns1, ne1, and ns2 are the start and end indices of the overlap on x1,
    # and the start index of the overlap on x2
    if indices is None:
        ns1, ne1, ns2 = get_domain_overlap(x1, x2)
    else:
        (ns1, ne1, ns2) = indices

    j = ns2
    dx1_sum = 0.0
    y1_sum = 0.0
    y2_sum = 0.0
    dy_sum = 0.0

    dx1_left = 0.0
    for i in range(ns1, ne1):
        j = get_left_index(x1[i], x2, j)
        slope = (y2[j + 1] - y2[j]) / (x2[j + 1] - x2[j])
        y2_interp = y2[j] + slope * (x1[i] - x2[j])

        dx1_right = 0.5 * (x1[i + 1] - x1[i])
        dx1 = dx1_left + dx1_right

        y1_sum = y1_sum + dx1 * fabs(y1[i])
        y2_sum = y2_sum + dx1 * fabs(y2_interp)
        dy_sum = dy_sum + dx1 * fabs(y1[i] - y2_interp)
        dx1_sum = dx1_sum + dx1

        # for next iteration
        dx1_left = dx1_right

    # Last interval
    i = ne1
    j = get_left_index(x1[i], x2, j)

    if x1[i] == x2[j]:
        y2_interp = y2[j]
    else:
        slope = (y2[j + 1] - y2[j]) / (x2[j + 1] - x2[j])
        y2_interp = y2[j] + slope * (x1[i] - x2[j])

    dx1 = dx1_left

    y1_sum = y1_sum + dx1 * fabs(y1[i])
    y2_sum = y2_sum + dx1 * fabs(y2_interp)
    dy_sum = dy_sum + dx1 * fabs(y1[i] - y2_interp)
    dx1_sum = dx1_sum + dx1

    # Done with last interval

    L1_y1 = y1_sum  # /dx1_sum
    L1_y2 = y2_sum  # /dx1_sum
    L1_dy = dy_sum  # /dx1_sum

    return L1_y1, L1_y2, L1_dy


def Linf_on_x1(x1, y1, x2, y2, indices=None):
    """Compute the L-infinity norm of y1, y2, and y2-y1 on an overlap
    region.

    y1_max = max(abs(y1_0), abs(y1_1), ... , abs(y1_i))
    y2_max = max(abs(y2_0), abs(y2_1), ... , abs(y2_i))
    dy_max = max(abs(dy_0), abs(dy_1), ... , abs(dy_i))
    dy = (y1-y2_interp)

    The overlap region is the common domain between x1 and
    x2. Before computing the norms, y2 data is interpolated onto
    x1. The norms are weighted by the spacing between the points in
    x1. Since data is always evaluated on x1, the ordering of the
    input arguments is important.

    indices is a tuple containing the results of
    get_domain_overlap(x1, x2)

    Return L-infinity norms of y1, y2, and (y2-y1)
    """

    # ns1, ne1, and ns2 are the start and end indices of the overlap on x1,
    # and the start index of the overlap on x2
    if indices is None:
        ns1, ne1, ns2 = get_domain_overlap(x1, x2)
    else:
        (ns1, ne1, ns2) = indices

    j = ns2

    y1_max = 0.0
    y2_max = 0.0
    dy_max = 0.0

    for i in range(ns1, ne1):
        j = get_left_index(x1[i], x2, j)

        slope = (y2[j + 1] - y2[j]) / (x2[j + 1] - x2[j])
        y2_interp = y2[j] + slope * (x1[i] - x2[j])

        y1_max = max(y1_max, fabs(y1[i]))
        y2_max = max(y2_max, fabs(y2_interp))
        dy_max = max(dy_max, fabs(y2_interp - y1[i]))

    # Last interval
    i = ne1
    j = get_left_index(x1[i], x2, j)

    if x1[i] == x2[j]:
        y2_interp = y2[j]
    else:
        slope = (y2[j + 1] - y2[j]) / (x2[j + 1] - x2[j])
        y2_interp = y2[j] + slope * (x1[i] - x2[j])

    y1_max = max(y1_max, fabs(y1[i]))
    y2_max = max(y2_max, fabs(y2_interp))
    dy_max = max(dy_max, fabs(y2_interp - y1[i]))

    # Done with last interval

    return y1_max, y2_max, dy_max


############################################################################


def process_tolerances(ilist, f1, f2, interpolate):
    diffs = 0

    L1 = f1.get_time_values()  # Same as x1 when finding norm
    L2 = f2.get_time_values()  # Same as x2 when finding norm
    x1 = L1
    x2 = L2

    assert len(ilist.times1) == len(ilist.times2)

    if not interpolate:
        if ilist.timetol is not None:
            tee.write("Time step values:")
            for j in range(len(ilist.times1)):
                i1 = ilist.times1[j]
                i2 = ilist.times2[j]
                d = ilist.timetol.difference(L1[i1], L2[i2])
                if d > ilist.timetol.tol:
                    tee.write(
                        "  times %15.8e & %15.8e %s diff = %10.3e"
                        % (L1[i1], L2[i2], ilist.timetol.diff, d)
                        + " (FAILED)"
                    )

    timeL = [L1[i] for i in ilist.times1]
    # compute time step sizes for centered around each time
    Delt = []
    if len(timeL) == 1:
        Delt.append(1.0)  # this is arbitrary
    elif len(timeL) > 1:
        Delt.append((timeL[1] - timeL[0]) / 2.0)
        for j in range(1, len(timeL) - 1):
            Delt.append((timeL[j + 1] - timeL[j - 1]) / 2.0)
        Delt.append((timeL[-1] - timeL[-2]) / 2.0)

    tee.write("Point variables:")
    for pid, pi1, pi2 in ilist.pointids:
        tee.write("   Point Id:", pid, "...")
        for n, ni1, ni2, tol in ilist.pointvars:
            if interpolate:
                L1 = f1.get_values(POINTVAR, ni1, pi1)
                L2 = f2.get_values(POINTVAR, ni2, pi2)
                result = tol.apply_prof_norm(L1, L2, x1, x2)
            else:
                L1 = f1.get_values(POINTVAR, ni1, pi1, ilist.times1)
                L2 = f2.get_values(POINTVAR, ni2, pi2, ilist.times2)
                result = tol.apply_norm(L1, L2, timeL, Delt)
            if result:
                tee.write("   %-20s" % (n) + result)
                diffs += 1

    tee.write("Material variables:")
    for mid, mi1, mi2 in ilist.matids:
        tee.write("   Material Id:", mid, "...")
        for n, ni1, ni2, tol in ilist.matvars:
            if interpolate:
                L1 = f1.get_values(MATVAR, ni1, mi1)
                L2 = f2.get_values(MATVAR, ni2, mi2)
                result = tol.apply_prof_norm(L1, L2, x1, x2)
            else:
                L1 = f1.get_values(MATVAR, ni1, mi1, ilist.times1)
                L2 = f2.get_values(MATVAR, ni2, mi2, ilist.times2)
                result = tol.apply_norm(L1, L2, timeL, Delt)
            if result:
                tee.write("   %-20s" % (n) + result)
                diffs += 1

    tee.write("Global variables:")
    for n, ni1, ni2, tol in ilist.globvars:
        if interpolate:
            L1 = f1.get_values(GLOBVAR, ni1)
            L2 = f2.get_values(GLOBVAR, ni2)
            result = tol.apply_prof_norm(L1, L2, x1, x2)
        else:
            L1 = f1.get_values(GLOBVAR, ni1, offsets=ilist.times1)
            L2 = f2.get_values(GLOBVAR, ni2, offsets=ilist.times2)
            result = tol.apply_norm(L1, L2, timeL, Delt)
        if result:
            tee.write("   %-20s" % (n) + result)
            diffs += 1

    return diffs


class HisDiffError(TestDiffed):
    ...
