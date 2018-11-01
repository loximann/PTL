#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
PyCTest driver for Parallel Tasking Library (PTL)
"""

import os
import sys
import shutil
import platform
import argparse
import traceback
import warnings
import multiprocessing as mp

import pyctest.pyctest as pyctest
import pyctest.pycmake as pycmake
import pyctest.helpers as helpers


#------------------------------------------------------------------------------#
def configure():

    # Get pyctest argument parser that include PyCTest arguments
    parser = helpers.ArgumentParser(project_name="PTL",
                                    source_dir=os.getcwd(),
                                    binary_dir=os.path.join(os.getcwd(), "build-PTL"),
                                    python_exe=sys.executable,
                                    build_type="Release",
                                    vcs_type="git",
                                    submit=False)

    parser.add_argument("--arch", help="PTL_USE_ARCH=ON",
                        default=False, action='store_true')
    parser.add_argument("--gperf", help="PTL_USE_GPERF=ON",
                        default=False, action='store_true')
    parser.add_argument("--tbb", help="PTL_USE_TBB=ON",
                        default=False, action='store_true')

    args = parser.parse_args()

    if os.path.exists(os.path.join(pyctest.BINARY_DIRECTORY, "CMakeCache.txt")):
        cm = helpers.FindExePath("cmake")
        cmd = pyctest.command([cm, "--build", pyctest.BINARY_DIRECTORY, "--target", "clean"])
        cmd.SetWorkingDirectory(pyctest.BINARY_DIRECTORY)
        cmd.SetOutputQuiet(True)
        cmd.SetErrorQuiet(True)
        cmd.Execute()
        for f in [ "CMakeCache.txt", "CMakeFiles" ]:
            helpers.RemovePath(os.path.join(pyctest.BINARY_DIRECTORY, f))

    if args.gperf:
        pyctest.copy_files(["gperf_cpu_profile.sh", "gperf_heap_profile.sh"],
            os.path.join(pyctest.SOURCE_DIRECTORY, ".scripts"),
            pyctest.BINARY_DIRECTORY)
        if pyctest.BUILD_TYPE == "Release":
            warnings.warn("Changing build type to 'RelWithDebInfo' when GPerf is enabled")
            pyctest.BUILD_TYPE = "RelWithDebInfo"

    return args


#------------------------------------------------------------------------------#
#
def run_pyctest():

    #--------------------------------------------------------------------------#
    # run argparse, checkout source, copy over files
    #
    args = configure()

    #--------------------------------------------------------------------------#
    # Set the build name
    #
    pyctest.BUILD_NAME = "[{}] [{} {} {}]".format(
        pyctest.GetGitBranch(pyctest.SOURCE_DIRECTORY),
        platform.uname()[0],
        helpers.GetSystemVersionInfo(),
        platform.uname()[4])

    #--------------------------------------------------------------------------#
    #   build specifications
    #
    if args.tbb:
        pyctest.BUILD_NAME = "{} [tbb]".format(pyctest.BUILD_NAME)
    if args.arch:
        pyctest.BUILD_NAME = "{} [arch]".format(pyctest.BUILD_NAME)
    if args.gperf:
        pyctest.BUILD_NAME = "{} [gperf]".format(pyctest.BUILD_NAME)

    #--------------------------------------------------------------------------#
    # how to build the code
    #
    pyctest.CONFIGURE_COMMAND = "${} -DPTL_USE_ARCH={} -DPTL_USE_GPERF={} -DPTL_USE_TBB={} -DCMAKE_BUILD_TYPE={} -DPTL_BUILD_EXAMPLES=ON {}".format(
        "{CTEST_CMAKE_COMMAND}", "ON" if args.arch else "OFF",
        "ON" if args.gperf else "OFF", "ON" if args.tbb else "OFF",
        pyctest.BUILD_TYPE, pyctest.SOURCE_DIRECTORY)

    #--------------------------------------------------------------------------#
    # how to build the code
    #
    pyctest.BUILD_COMMAND = "${} --build {} --target all".format(
        "{CTEST_CMAKE_COMMAND}", pyctest.BINARY_DIRECTORY)

    #--------------------------------------------------------------------------#
    # parallel build
    #
    if platform.system() != "Windows":
        pyctest.BUILD_COMMAND = "{} -- -j{}".format(
            pyctest.BUILD_COMMAND, mp.cpu_count())
    else:
        pyctest.BUILD_COMMAND = "{} -- /MP -A x64".format(pyctest.BUILD_COMMAND)


    #--------------------------------------------------------------------------#
    # how to update the code
    #
    git_exe = helpers.FindExePath("git")
    pyctest.UPDATE_COMMAND = "{}".format(git_exe)
    pyctest.set("CTEST_UPDATE_TYPE", "git")
    pyctest.set("CTEST_GIT_COMMAND", "{}".format(git_exe))

    #--------------------------------------------------------------------------#
    # static analysis
    #
    clang_tidy_exe = helpers.FindExePath("clang-tidy")
    if clang_tidy_exe:
        pyctest.set("CMAKE_CXX_CLANG_TIDY",
                    "{};-checks=*".format(clang_tidy_exe))

    #--------------------------------------------------------------------------#
    # find the CTEST_TOKEN_FILE
    #
    if args.pyctest_token_file is None and args.pyctest_token is None:
        home = helpers.GetHomePath()
        if home is not None:
            token_path = os.path.join(
                home, os.path.join(".tokens", "nersc-cdash"))
            if os.path.exists(token_path):
                pyctest.set("CTEST_TOKEN_FILE", token_path)

    #--------------------------------------------------------------------------#
    # construct a command
    #
    def construct_command(cmd, args):
        _cmd = []
        if args.gperf:
            _cmd.append(os.path.join(pyctest.BINARY_DIRECTORY,
                                     "gperf_cpu_profile.sh"))
        _cmd.extend(cmd)
        return _cmd

    #--------------------------------------------------------------------------#
    # standard environment settings for tests, adds profile to notes
    #
    def test_env_settings(prof_fname, clobber=False):
        if args.gperf:
            pyctest.add_note(pyctest.BINARY_DIRECTORY,
                            "{}.txt".format(prof_fname),
                            clobber=clobber)
            pyctest.add_note(pyctest.BINARY_DIRECTORY,
                            "{}.cum.txt".format(prof_fname),
                            clobber=False)
        return "PTL_NUM_THREADS={};CPUPROFILE={};CUTOFF_LOW={}".format(
            mp.cpu_count(), prof_fname, 15)

    #--------------------------------------------------------------------------#
    # create tests
    #
    test = pyctest.test()
    test.SetName("tasking")
    test.SetProperty("WORKING_DIRECTORY", pyctest.BINARY_DIRECTORY)
    test.SetProperty("ENVIRONMENT", test_env_settings(
        "cpu-prof-tasking", clobber=True))
    test.SetProperty("RUN_SERIAL", "ON")
    test.SetCommand(construct_command(["./tasking"], args))

    test = pyctest.test()
    test.SetName("recursive_tasking")
    test.SetProperty("WORKING_DIRECTORY", pyctest.BINARY_DIRECTORY)
    test.SetProperty("ENVIRONMENT", test_env_settings(
        "cpu-prof-recursive-tasking"))
    test.SetProperty("RUN_SERIAL", "ON")
    test.SetCommand(construct_command(["./recursive_tasking"], args))

    if args.tbb:
        test = pyctest.test()
        test.SetName("tbb_tasking")
        test.SetProperty("WORKING_DIRECTORY", pyctest.BINARY_DIRECTORY)
        test.SetProperty("ENVIRONMENT", test_env_settings(
            "cpu-prof-tbb-tasking"))
        test.SetProperty("RUN_SERIAL", "ON")
        test.SetCommand(construct_command(["./tbb_tasking"], args))

        test = pyctest.test()
        test.SetName("recursive_tbb_tasking")
        test.SetProperty("WORKING_DIRECTORY", pyctest.BINARY_DIRECTORY)
        test.SetProperty("ENVIRONMENT", test_env_settings(
            "cpu-prof-tbb-recursive-tasking"))
        test.SetProperty("RUN_SERIAL", "ON")
        test.SetCommand(construct_command(["./recursive_tbb_tasking"], args))

    pyctest.generate_config(pyctest.BINARY_DIRECTORY)
    pyctest.generate_test_file(pyctest.BINARY_DIRECTORY)
    pyctest.run(pyctest.ARGUMENTS, pyctest.BINARY_DIRECTORY)


#------------------------------------------------------------------------------#
if __name__ == "__main__":

    try:

        run_pyctest()

    except Exception as e:
        print('Error running pyctest - {}'.format(e))
        exc_type, exc_value, exc_trback = sys.exc_info()
        traceback.print_exception(exc_type, exc_value, exc_trback, limit=10)
        sys.exit(1)

    sys.exit(0)
