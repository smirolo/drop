#!/usr/bin/env python
#
# Copyright (c) 2009-2011, Fortylines LLC
#   All rights reserved.
#
#   Redistribution and use in source and binary forms, with or without
#   modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of fortylines nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
#   THIS SOFTWARE IS PROVIDED BY Fortylines LLC ''AS IS'' AND ANY
#   EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
#   WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
#   DISCLAIMED. IN NO EVENT SHALL Fortylines LLC BE LIABLE FOR ANY
#   DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
#   (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
#   LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
#   ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#  (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
#   SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# Generate regression between two log files.
#
# Primary Author(s): Sebastien Mirolo <smirolo@fortylines.com>

import re, os, optparse, shutil, stat, sys, tempfile, time
import cStringIO

__version__ = None

class TestCaseFormater:

    def __init__(self, testName, fileobj):
        self.testName = testName
        self.out = fileobj
        self.out.write('<testcase name="%s" classname="%s" time="0">\n' \
                           % (self.testName, self.testName))

    @staticmethod
    def associate(name,fileobj):
        return TestCaseFormater(name,fileobj)

    def header(self,tag,reffile,testStatus):
        self.tag = tag
        self.out.write('<%s name="%s">\n' % (tag,reffile))
        self.out.write('<status>%s</status>\n' % (testStatus))
        self.out.write('<system-out><![CDATA[\n')

    def flush(self):
        self.out.write('</testcase>\n')

    def footer(self):
        self.out.write(']]></system-out>\n')
        self.out.write('</%s>\n' % self.tag)

    def write(self, text):
        self.out.write(text)


class JUnitFormater(TestCaseFormater):

    def __init__(self, testName, fileobj):
        self.testName = testName
        self.out = fileobj
        self.tag = None

    @staticmethod
    def associate(name,fileobj):
        return JUnitFormater(name,fileobj)

    def header(self,tag,reffile,testStatus):
        name = os.path.basename(os.path.splitext(reffile)[0])
        self.out.write('<testcase name="%s" classname="%s" time="0">\n' \
                           % (name, self.testName))
        if testStatus == 'absent':
            self.tag = None
        elif testStatus == 'compile':
            self.tag = None
        elif testStatus == 'identical':
            self.tag = None
        elif testStatus == 'pass':
            self.tag = None
        else:
            # testStatus in [ 'different', 'unknown' ] and everything else
            self.out.write('<error type="%s"><![CDATA[\n' % tag)
            self.tag = testStatus

    def flush(self):
        None

    def footer(self):
        if self.tag:
            self.out.write(']]></error>\n')
        self.out.write('</testcase>\n')

    def write(self, text):
        if self.tag:
            self.out.write(text)


def diffAdvance(diff,testFile = None):
    diffLineNum = sys.maxint
    look = None
    while look == None:
        diffLine = diff.readline()
        if diffLine == '':
            break
        if testFile:
            testFile.write(diffLine)
        look = re.match('@@ -(\d+),',diffLine)
    if look != None:
        # The "diff -U 1" is invoked. This seems to all offset all starting
        # chunks by 1. In case the test result is only one line long, it might
        # indicate the wrong test as "different" in a regression.
        diffLineNum = int(look.group(1)) + 1
    return diffLineNum


def logAdvance(log):
    logLine = log.readline()
    if logLine == '':
        logLineNum = sys.maxint
        logTestName = None
    else:
        look = re.match('(\d+):@@ test: (\S+) (\S+)? @@',logLine)
        if look != None:
            logLineNum = int(look.group(1))
            logTestName = look.group(2)
            # group(3) if present is status
        else:
            raise dws.Error("unexpected format of result log. Line '" \
                                + logLine + "' does not match " \
                                + "'(\d+):@@ test: (\S+) (\S+)? @@'.")
    return logLineNum, logTestName


# Main Entry point
if __name__ == '__main__':
    usage= 'usage: %prog [options] -o regression result [reference ...]'
    parser = optparse.OptionParser(usage=usage,
                                   version='%prog ' + str(__version__))
    parser.add_option('--format', dest='format',
                      default='junit',
                      help='format of the log output (currently only junit is supported)')
    parser.add_option('-o', dest='output',
                      metavar="FILE",
                      default='regression.log',
                      help='Output regression log FILE')
    parser.add_option('--help-book', dest='helpBook', action='store_true',
                      help='Print help in docbook format')

    options, args = parser.parse_args()

    if options.helpBook:
        import imp
        dws = imp.load_source('dws',
            os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])),'dws'))
        help = cStringIO.StringIO()
        parser.print_help(help)
        dws.helpBook(help)
        sys.exit(0)

    testFormater = TestCaseFormater
    if options.format == 'junit':
        testFormater = JUnitFormater

    if len(args) < 1:
        parser.print_help()
        sys.exit(1)

    logfile = args[0]
    reffiles = args[1:]

    tests = {}
    regressions = {}
    for reffile in reffiles:
        logCmdLine = "grep -n '@@ test:' " + logfile
        # Use one line of context such that a "first line" diff does
        # not include "previous test" output in the context because
        # that would change value of diffLineNum and mess the following
        # algorithm.
        diffCmdLine = 'diff -U 1 ' + logfile + ' ' + reffile
        #print "!!! log cmd line: " + logCmdLine
        #print "!!! diff cmd line: " + diffCmdLine
        log = os.popen(logCmdLine)
        diff = os.popen(diffCmdLine)

        # Find the line on which the first test output starts. Skip
        # the difference in the logs before that point as they don't
        # refer to any test. The line on which the second test output
        # starts marks the end of a difference range associated
        # with *prevLogTestName*.
        logLineNum, prevLogTestName = logAdvance(log)
        if not prevLogTestName in tests:
            tests[prevLogTestName] = testFormater.associate(prevLogTestName,
                                                     tempfile.TemporaryFile())
        if not prevLogTestName in regressions:
            regressions[prevLogTestName] = {}
        diffLineNum = diffAdvance(diff)
        while diffLineNum < logLineNum:
            diffLineNum = diffAdvance(diff)
        logLineNum, logTestName = logAdvance(log)
        if not logTestName in regressions:
            regressions[logTestName] = {}

        # end-of-file is detected by checking the uninitialized value
        # of logLineNum and diffLineNum as set by logAdvance()
        # and diffAdvance().
        testFile = None
        while logLineNum != sys.maxint and diffLineNum != sys.maxint:
            #print "!!! " + str(prevLogTestName) \
            #    + ', log@' + str(logLineNum) \
            #    + ' ' + str(logTestName) + ' and diff@' + str(diffLineNum)
            if diffLineNum < logLineNum:
                # last log failed
                if prevLogTestName != None:
                    if not prevLogTestName in tests:
                        tests[prevLogTestName] \
                            = testFormater.associate(prevLogTestName,
                                                      tempfile.TemporaryFile())
                    testFile = tests[prevLogTestName]
                    if not prevLogTestName in regressions:
                        regressions[prevLogTestName] = {}
                    if not reffile in regressions[prevLogTestName]:
                        testStatus = "different"
                        testFile.header('compare',reffile,testStatus)
                        regressions[prevLogTestName][reffile] = testStatus
                    prevLogTestName = None
                diffLineNum = diffAdvance(diff,testFile)
            elif diffLineNum > logLineNum:
                # last log passed
                if prevLogTestName != None:
                    if not prevLogTestName in tests:
                        tests[prevLogTestName] \
                            = testFormater.associate(prevLogTestName,
                                                      tempfile.TemporaryFile())
                    testFile = tests[prevLogTestName]
                    if not prevLogTestName in regressions:
                        regressions[prevLogTestName] = {}
                    if not reffile in regressions[prevLogTestName]:
                        testStatus = "identical"
                        testFile.header('compare',reffile,testStatus)
                        regressions[prevLogTestName][reffile] = testStatus
                prevLogTestName = logTestName
                logLineNum, logTestName = logAdvance(log)
            else:
                if prevLogTestName != None:
                    if not prevLogTestName in tests:
                        tests[prevLogTestName] \
                            = testFormater.associate(prevLogTestName,
                                                      tempfile.TemporaryFile())
                    testFile = tests[prevLogTestName]
                    if not prevLogTestName in regressions:
                        regressions[prevLogTestName] = {}
                    if not reffile in regressions[prevLogTestName]:
                        testStatus = "identical"
                        testFile.header('compare',reffile,testStatus)
                        regressions[prevLogTestName][reffile] = testStatus
                prevLogTestName = logTestName
                logLineNum, logTestName = logAdvance(log)
                diffLineNum = diffAdvance(diff,testFile)

        # If we donot have any more differences and we haven't
        # reached the end of the list of tests, all remaining
        # tests must be identical or be absent...
        if logLineNum != sys.maxint:
            # Gather all the tests in the reference file in order
            # to distinguish between identical and absent.
            refs = set([])
            reflogCmdLine = "grep -n '@@ test:' " + reffile
            reflog = os.popen(reflogCmdLine)
            reflogLineNum, reflogTestName = logAdvance(reflog)
            while reflogLineNum != sys.maxint:
                refs |= set([ reflogTestName ])
                reflogLineNum, reflogTestName = logAdvance(reflog)
            reflog.close()
            while logLineNum != sys.maxint:
                if logTestName in refs:
                    if not logTestName in regressions:
                        regressions[logTestName] = {}
                    if not reffile in regressions[logTestName]:
                        testStatus = "identical"
                        testFile.header('compare',reffile,testStatus)
                        regressions[logTestName][reffile] = testStatus
                logLineNum, logTestName = logAdvance(log)
        elif logLineNum == diffLineNum:
            # Both finish at the same time, let's flush the last testName
            # and be done with it. It seems the test is new and wasn't run
            # in the reference.
            if prevLogTestName != None:
                if not prevLogTestName in tests:
                    tests[prevLogTestName] \
                        = testFormater.associate(prevLogTestName,
                                                  tempfile.TemporaryFile())
                testFile = tests[prevLogTestName]
                if not prevLogTestName in regressions:
                    regressions[prevLogTestName] = {}
                if not reffile in regressions[prevLogTestName]:
                    testStatus = "absent"
                    testFile.header('compare',reffile,testStatus)
                    regressions[prevLogTestName][reffile] = testStatus
                prevLogTestName = None
        diff.close()
        log.close()
        for testName in tests:
            tests[testName].footer()

    # All diffs have been computed, let's print out the regressions.
    # We are going to output an XML file which is suitable to display
    # as a table with a row per test and a column per reference log.

    # 1. Merge result files together in a single file such that information
    #    associated with a test ends up under the same tag.'''
    testFile = None
    nbFailures = 0
    failureNames = set([])
    (confno, confname) = tempfile.mkstemp()
    os.close(confno)
    conf = open(confname,'w')
    firstIteration = True
    for filename in args:
        hasOuput = {}
        f = open(filename,'r')
        line = f.readline()
        while line != '':
            look = re.match('@@ test: (\S+) (\S+)?\s*@@',line)
            if look:
                # found information associated with a test
                testName = look.group(1)
                if look.group(2):
                    testStatus = look.group(2)
                else:
                    testStatus = 'unknown'
                if firstIteration and testStatus != 'pass':
                    failureNames |= set([testName])
                    nbFailures = nbFailures + 1
                if not testName in tests:
                    tests[testName] = testFormater.associate(testName,
                                                    tempfile.TemporaryFile())
                tests[testName].header('result',filename,testStatus)
                testFile = tests[testName]
                hasOuput[testName] = True
            elif testFile:
                testFile.write(line)
            else:
                conf.write(line)
            line = f.readline()
        f.close()
        for testName in hasOuput:
            tests[testName].footer()
        firstIteration = False

    # Complete the missing cases for tests which were removed,
    # did not compile, etc.
    nbRegressions = 0
    regressionNames = {}
    for testName in sorted(tests):
        for reffile in reffiles:
            if testName in regressions:
                if reffile in regressions[testName]:
                    # The test might not appear in the reference file
                    # if it was created after the reference was generated.
                    # There are no regressions there is nothing to compare
                    # against.
                    if regressions[testName][reffile] == 'different':
                        if not reffile in regressionNames:
                            regressionNames[reffile] = set([])
                        regressionNames[reffile] \
                            |= set([testName])
                        nbRegressions = nbRegressions + 1
                    testStatus = regressions[testName][reffile]
                else:
                    tests[testName].header('compare',reffile,'absent')
                    tests[testName].footer()
            else:
                if not reffile in regressionNames:
                    regressionNames[reffile] = set([])
                regressionNames[reffile] |= set(['- ' + testName])
                nbRegressions = nbRegressions + 1
                if not testName in tests:
                    tests[testName] = testFormater.associate(testName,
                                                    tempfile.TemporaryFile())
                tests[testName].header('compare',reffile,'compile')
                tests[testName].footer()

    if False:
        # \todo do we need to set those anymore?
        #       Yes in order to easily generate columns headers
        # 2. Write the reference files against which comparaison is done.
        for reffile in reffiles:
            id = os.path.splitext(os.path.basename(reffile))[0]
            conf.write('<reference id="' + id \
                           + '" name="' + reffile + '"/>\n')

    # Results for a single testcase have been aggregated in a temporary file.
    # Let's build the final file.
    testsuitename = "testsuite"
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S",
                              time.gmtime(os.path.getmtime(logfile)))
    # timestamp = datetime.datetime(os.stat(logfile).st_mtime)
    time = 0 # time taken to execute testsuite
    hostname = "localhost"
    expectedFail = 0
    (outno, outname) = tempfile.mkstemp()
    os.close(outno)
    out = open(outname,'w')
    out.write('<testsuite name="%s" timestamp="%s" time="%s" hostname="%s" tests="%d" failures="%s" errors="%s">\n' \
       % (testsuitename, timestamp, time, hostname,
          len(tests), expectedFail, nbFailures))
    out.write('<properties></properties>\n')

    if False:
        # Properties does seem appropriate. We used to put the system
        # configuration here.
        conf = open(confname)
        line = conf.readline()
        while line != '':
            out.write(line)
            line = conf.readline()
        conf.close()

    # print "!!! regressions=" + str(regressions)

    # 3. All temporary files have been created, it is time to merge
    #    them back together.
    for testName in sorted(tests):
        testFile = tests[testName]
        testFile.flush()
        testFile.out.seek(0,os.SEEK_SET)
        line = testFile.out.readline()
        while line != '':
            out.write(line)
            line = testFile.out.readline()
        testFile.out.close()

    if options.format == 'junit':
        out.write('<system-out><![CDATA[\n')
        log = open(logfile)
        line = log.readline()
        while line != '':
            out.write(line)
            line = log.readline()
        log.close()
        out.write(']]></system-out>\n')
        out.write('<system-err><![CDATA[\n')
        out.write(']]></system-err>\n')

    out.write('</testsuite>\n')
    out.close()
    # Insures permission will allow the CGI to read the file
    os.chmod(outname,stat.S_IRUSR | stat.S_IWUSR
             | stat.S_IRGRP | stat.S_IROTH)
    shutil.move(outname,options.output)
    sys.stdout.write(str(nbFailures) + ' failures\n')
    if len(failureNames) > 0:
        sys.stdout.write('\t' + '\n\t'.join(failureNames) + '\n')
    sys.stdout.write(str(nbRegressions) + ' regressions\n')
    if len(regressionNames) > 0:
        for reffile in regressionNames:
            sys.stdout.write('\t(' + os.path.basename(reffile) + ')\n')
            sys.stdout.write('\t' \
                + '\n\t'.join(regressionNames[reffile]) + '\n')
    sys.exit(max(nbFailures,nbRegressions))



