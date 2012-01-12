# Copyright (c) 2011 Mark A. Tsuchida
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

import contextlib
import os
import pexpect
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import warnings
import weakref

# A list of weakrefs to all plots ever created.
_allplots = []

class CommunicationError(RuntimeError):
    """Raised when communication with Gnuplot subprocess failed."""

class GnuplotError(RuntimeError):
    """Raised when Gnuplot (is known to have) responded with an error."""

class RawGnuplot(object):
    """Low-level manager for communication with a Gnuplot subprocess."""

    gp_prompt = "gnuplot> "
    send_chunk_length = 512

    def __init__(self, command=None, persist=False, tempdir=None,
                 testecho=False):
        """Return a new Gnuplot object.

        Keyword Arguments:
        command - The command used to invoke Gnuplot. Defaults to `gnuplot',
                  unless the environment variable XNUPLOT_GNUPLOT is defined,
                  in which case its value is used.
        persist - Whether the plot window should stay open after this object
                  (and hence the Gnuplot subprocess) is destroyed.
        tempdir - Directory to use for temporary data. A new directory is
                  created within the given directory, whose name is stored in
                  self.tempdir.
        testecho - Check to see if the assumptions we make about how Gnuplot
                   echoes commands are correct. Try setting this to True if
                   you suspect xnuplot is not properly communicating with
                   Gnuplot.
        """
        self._debug = False
        self.tempdir = tempfile.mkdtemp(prefix="xnuplot.", dir=tempdir)

        if not command:
            if "XNUPLOT_GNUPLOT" in os.environ:
                command = os.environ["XNUPLOT_GNUPLOT"]
            else:
                command = "gnuplot"

        if persist:
            command += " -persist"
        try:
            self.gp_proc = pexpect.spawn(command)
            self.gp_proc.delaybeforesend = 0
        except:
            os.rmdir(self.tempdir)
            raise

        ok = False
        try:
            self.gp_proc.expect_exact(self.gp_prompt)
            ok = True
        except pexpect.EOF:
            raise CommunicationError("Gnuplot died before showing prompt")
        except pexpect.TIMEOUT:
            raise CommunicationError("timeout")
        finally:
            if not ok:
                self.terminate()

        if testecho:
            self._test_readline_echo()

        global _allplots
        _allplots.append(weakref.ref(self))

    def __enter__(self):
        return self
    def __exit__(self, type, value, traceback):
        self.close()
    def __del__(self):
        self.close()

    def close(self):
        """Close the Gnuplot subprocess and remove all temporary files."""
        # Soft quitting is no different from force-quitting.
        self.terminate()

    def terminate(self):
        """Force-quit the Gnuplot subprocess and remove all temporary files."""
        if self.gp_proc is not None:
            self.gp_proc.close(force=True)
            self.gp_proc = None
        if self.tempdir:
            shutil.rmtree(self.tempdir)
            self.tempdir = None

    def isalive(self):
        return self.gp_proc is not None and self.gp_proc.isalive()

    def __call__(self, command, **data):
        """Send a command (or commands) to Gnuplot.

        The output from Gnuplot is returned as a string. If command contains
        multiple lines, nonempty outputs from each command are concatenated
        with newlines as separators. Thus, if none of the commands printed
        anything, an empty string is returned.

        A special mechanism is provided to send data to Gnuplot, using what
        Gnuplot calls a `datafile'. This can be done by placing strings of the
        form `{{foo}}' (we call this a data placefolder with name `foo') within
        the command, where normally a quoted filename would appear. Then, the
        data that Gnuplot should read should be supplied as a keyword argument.
        The data can be any object that, when written to a file, generates the
        correct representation for Gnuplot.

        For example:
        gp = Gnuplot()
        gp("plot {{data}} volatile notitle with lines", data="1 2\n2 1\n3 3")

        The actual passing of data is achieved, by default, through the use of
        named pipes (FIFOs). This works well most of the time, but there are
        some cases where Gnuplot requires random access to the data, where
        pipes fail (one example of this is the `binary matrix' data format). To
        handle such cases, use of a temporary file can be forced by the syntax
        `{{file:foo}}'. The default syntax (`{{foo}}') is equivalent to
        `{{pipe:foo}}'.
        """
        if not self.isalive():
            raise CommunicationError("Gnuplot process has exited.")
        results = []
        for cmd in command.split("\n"):
            result = self._send_one_command(cmd, **data)
            if result is None:
                # None is returned when Gnuplot exited normally.
                break
            if result:
                results.append(result)
        return "\n".join(results)

    _placeholder_pattern = re.compile(
            r"\{\{((?P<mode>file|pipe):)?(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\}\}")
    @contextlib.contextmanager
    def _placeholders_substituted(self, command, **data):
        substituted_command = ""
        start_of_next_chunk = 0 # Position after current placeholder.
        pipes = []
        for placeholder in self._placeholder_pattern.finditer(command):
            name = placeholder.group("name")
            mode = placeholder.group("mode")
            pipeclass = (_OutboundTempFile if mode == "file"
                         else _OutboundNamedPipe)
            pipe = pipeclass(data[name], dir=self.tempdir)
            pipe.debug = self.debug
            pipes.append(pipe)
            span_start, span_stop = placeholder.span(0)
            substituted_command += command[start_of_next_chunk:span_start]
            substituted_command += Gnuplot.quote(pipe.path)
            start_of_next_chunk = span_stop
        substituted_command += command[start_of_next_chunk:]
        yield substituted_command
        for pipe in pipes:
            pipe.cleanup()

    def _sendline(self, line):
        # The os.write() call used by pexpect seems to hang when the string
        # sent is too long, at least on Mac OS X and Gnuplot built with GNU
        # readline. Merely sending the line in small chunks does not prevent
        # the hangs; it is necessary to read the echo after each chunk is sent.
        # (Thus, it appears that Gnuplot or libreadline blocks on the echo
        # write.) To work around this issue, we send the line in small chunks
        # and make pexpect read and buffer the echo after each send.
        chunk_length = self.send_chunk_length
        n_nonend_chunks = len(line) // chunk_length
        for i in xrange(n_nonend_chunks):
            start = i * chunk_length
            stop = start + chunk_length
            self.gp_proc.send(line[start:stop])
            # Cause pexpect to read in the echo.
            self.gp_proc.expect(pexpect.TIMEOUT, timeout=0)
        start = n_nonend_chunks * chunk_length
        self.gp_proc.sendline(line[start:])
        # Skip over the echoed command (see _test_readline_echo()).
        self.gp_proc.expect_exact("\r\n")

    def _send_one_command(self, command, _extra_newline=False, **data):
        # Do the acutal work for __call__().
        with self._placeholders_substituted(command, **data) as command:
            try:
                self._sendline(command)
            except KeyboardInterrupt, e:
                # Kill Gnuplot if it hangs and the user terminates the
                # command.
                self.terminate()
                raise CommunicationError("killed by user")
            if _extra_newline:
                self.gp_proc.sendline("")

            try:
                self.gp_proc.expect_exact(self.gp_prompt)
                result = self.gp_proc.before
                if _extra_newline:
                    self.gp_proc.expect_exact(self.gp_prompt)
                return result.replace("\r\n", "\n")
            except pexpect.EOF:
                self.terminate()
                if re.match(r"\s*(quit|exit)(\W|$)", command):
                    return None
                else:
                    raise CommunicationError("Gnuplot died")
            except pexpect.TIMEOUT:
                self.terminate()
                raise CommunicationError("timeout")

    def pause(self, *params):
        command = " ".join(("pause",) + params)
        # At least with the tested build of Gnuplot 4.4.0 on Mac OS X, closing
        # the window does not cause `pause mouse close' to immediately return. 
        # Sending an extra newline appears to get around the block, so here is
        # a special workaround.
        send_extra_newline = False
        if len(params) and params[0].startswith("mouse"):
            send_extra_newline = True

        # Temporarily disable the timeout for a `pause' command.
        save_timeout = self.timeout
        try:
            self.timeout = None
            self._send_one_command(command, _extra_newline=send_extra_newline)
        finally:
            if self.isalive():
                self.timeout = save_timeout

    def _test_readline_echo(self):
        # Determine how Gnuplot echoes the command. If Gnuplot is built without
        # readline support, it will simply let the tty do the echo. However, if
        # built with readline support (builtin, GNU readline, or BSD libedit),
        # then it will turn off the tty echo and echo each input character on
        # its own. Thus, we expect to receive an echo regardless of what
        # gp_proc.getecho() reports.
        #
        # To further complicate matters, GNU readline and BSD libedit insert
        # control characters into the echoed text, in an attempt to move the
        # cursor to the beginning of the next line whenever a character is
        # entered in what would be the rightmost column of a real terminal.
        # This causes us to see the sequence " \r" (GNU) or " \b" (BSD) every
        # 80 characters (or whatever the width of the tty), at least with the
        # versions I've tested (Gnuplot's builtin readline does not insert any
        # extra characters). The exact behavior may also depend on the
        # particular terminal in use.
        #
        # Fortunately, we can still just skip over to the first "\r\n" in
        # all of the known cases. We just make sure here that these assumptions
        # hold.

        unknown_behavior_msg = ("Gnuplot is echoing commands in an unexpected "
                                "fashion. Xnuplot does not (yet) know how to "
                                "handle this. Please file a bug report. ")
        # First, test a single-character command line.
        self.gp_proc.sendline("#")
        self.gp_proc.expect_exact(self.gp_prompt)
        echo = self.gp_proc.before
        if echo != "#\r\n":
            raise CommunicationError(unknown_behavior_msg +
                                     "(\"#\" -> \"{0}\")".format(repr(echo)))
        # Second, test a command line long enough to be wrapped.
        rows, cols = self.gp_proc.getwinsize()
        test_cmd = "#" * (cols * 3)
        self.gp_proc.sendline(test_cmd)
        self.gp_proc.expect_exact(self.gp_prompt)
        echo = self.gp_proc.before[:-2] # Remove trailing "\r\n".
        if echo == test_cmd:
            # Okay: exact echo.
            return
        breaks = filter(None, echo.split("#"))
        for b in breaks[1:]:
            if b != breaks[0]:
                raise CommunicationError(unknown_behavior_msg +
                                         "(nonuniform linebreaks)")
        if "\r\n" in breaks[0]:
            raise CommunicationError(unknown_behavior_msg +
                                     "(extra CRLFs inserted)")
        else:
            # Okay: whatever is inserted into the echo, it does not contain
            # the "\r\n" sequence.
            return

    def interact(self):
        """Interact directly with the Gnuplot subprocess.

        Handles control of the subprocess to the user.
        The interactive session can be terminated by typing CTRL-].
        """
        if not self.isalive():
            raise CommunicationError("Gnuplot process has exited.")
        # Debug mode (echoing) is a mere annoyance when in interactive mode.
        @contextlib.contextmanager
        def debug_turned_off():
            save_debug = self.debug
            self.debug = False
            yield
            self.debug = save_debug
        with debug_turned_off():
            print >>sys.stderr, "escape character is `^]'"
            # Send a black command so that the prompt is printed.
            self.gp_proc.sendline("")
            self.gp_proc.interact()

        # The user could have quit Gnuplot.
        if not self.gp_proc.isalive():
            self.terminate()

    @property
    def timeout(self):
        "Timeout (in seconds) for replies from Gnuplot."
        if not self.isalive():
            raise CommunicationError("Gnuplot process has exited.")
        return self.gp_proc.timeout

    @timeout.setter
    def timeout(self, seconds):
        if not self.isalive():
            raise CommunicationError("Gnuplot process has exited.")
        self.gp_proc.timeout = seconds

    @property
    def debug(self):
        "Echo communication with Gnuplot if true."
        return self._debug

    @debug.setter
    def debug(self, debug):
        self._debug = debug
        if self.isalive():
            self.gp_proc.logfile_read = (sys.stderr if debug else None)

    @staticmethod
    def quote(filename):
        """Return a quoted string for use as part of a Gnuplot command."""
        quoted =  "'" + filename.replace("\\", "\\\\").replace("'", "\\'") + "'"
        return quoted

class Gnuplot(RawGnuplot):
    """Manager for communication with a Gnuplot subprocess."""
    def _datafilespec(self, data, name):
        if not isinstance(data, PlotData):
            data = PlotData(*data)
        double_brace = lambda s: "{{" + s + "}}"
        if data.mode == "file":
            spec = double_brace("file:{0}".format(name))
        else:
            spec = double_brace("pipe:{0}".format(name))
        spec += " volatile"
        if data.options:
            spec = " ".join((spec, data.options))
        return spec, data.data

    def _plot(self, cmd, *items):
        if not items:
            return
        # Common implementation for plot() and splot().
        item_strings = []
        data_dict = {}
        for i, item in enumerate(items):
            if isinstance(item, basestring):
                item_strings.append(item)
            else:
                placeholder = "item{0:03d}".format(i)
                spec, data = self._datafilespec(item, placeholder)
                item_strings.append(spec)
                data_dict[placeholder] = data
        result = self(cmd + " " + ", ".join(item_strings), **data_dict)
        # Result should be the empty string if successful.
        if len(result):
            # Remove Gnuplot's syntax error pointer.
            msg = result.strip().lstrip("^").strip()
            raise GnuplotError("`{0}' returned error".format(cmd), msg)

    def plot(self, *items):
        """Issue a `plot' command with the given items.

        Each item can be a string, a PlotData instance, or a tuple (which is
        used as the argument list to construct a PlotData instance).

        See also: splot(), replot()

        Example:
        Gnuplot().plot("sin(x) notitle", "'some_file.dat' with lp",
                       (some_data, "binary array=(512,512) with image"))
        """
        self._plot("plot", *items)

    def splot(self, *items):
        """Issue an `splot' command with the given items.

        See the documentation for plot().
        """
        self._plot("splot", *items)

    def replot(self, *items):
        """Issue a `replot' command with the given items.

        See the documentation for plot().

        Note that `replot' does not work when the previous plot was made by
        passing data to Gnuplot, unless temporary files were used explicitly.
        """
        self._plot("replot", *items)

    def fit(self, data, expr, via, ranges=None):
        """Issue a `fit' command.

        As with the items in plot(), data can be a PlotData instance or a tuple
        (which is used as the argument list to construct a PlotData), but not a
        string.
        The other arguments (expr, via, and ranges) must be strings.
        """
        spec, fitdata = self._datafilespec(data, "fitdata")
        cmd = " ".join(filter(None, ("fit", ranges, expr, spec, "via", via)))
        return self(cmd, fitdata=fitdata)

    def source(self, script):
        """Issue a `load' command, piping the given script as input."""
        if not script.endswith("\n"):
            script += "\n"
        return self("load {{script}}", script=script)

class PlotData(object):
    """Wrapper for a data item in a Gnuplot `plot' or `splot' command."""
    __slots__ = ("data", "options", "mode")

    def __init__(self, data, options=None, mode=None):
        """Initialize a PlotData object.

        Arguments:
        data    - The data to be sent to Gnuplot.
        options - Datafile modifiers and plot options for the command line (a
                  string, such as "using 2:1 with linespoints").
        mode    - One of "pipe" or "file". If "file", a temporary file will be
                  used to pass the data to Gnuplot. This can be useful if you
                  want to send `binary matrix' data, which doesn't work with
                  named pipes. By default ("pipe"), a named pipe is used.
        """
        self.data = data
        self.options = options
        if mode is None:
            mode = "pipe"
        if mode not in ("pipe", "file"):
            raise ValueError('PlotData mode must be either "pipe" or "file"')
        self.mode = mode

    def __repr__(self):
        data_str = " source=" + type(self.data).__name__
        options_str = " options=" + repr(self.options) if self.options else ""
        mode_str = " mode=file" if self.mode == "file" else " mode=pipe"
        return "<PlotData{0}{1}{2}>".format(data_str, options_str, mode_str)

class _OutboundNamedPipe(threading.Thread):
    # Asynchronous manager for named pipe for sending data.
    # Once constructed, takes responsibility for cleanup after data is sent.
    def __init__(self, data, dir=None):
        self.data = data
        self.debug = False
        if dir:
            self.dir = dir
            self.made_dir = False
        else:
            self.dir = tempfile.mkdtemp()
            self.made_dir = True
        self.path = tempfile.mktemp(prefix="fifo.", dir=self.dir)
        super(_OutboundNamedPipe, self).__init__(name=self.path)
        # Make the named pipe synchronously, so that it's guaranteed to be
        # ready for immediate use by the reader.
        os.mkfifo(self.path)
        self.start()

    def cleanup(self):
        # Cleanup is done in run() to avoid race conditions.
        pass

    def run(self):
        try:
            with open(self.path, "wb") as pipe:
                pipe.write(self.data)
            if self.debug:
                msg = "<<wrote {0} bytes to pipe {1}>>".format(len(self.data),
                                                               self.path)
                print >>sys.stderr, msg
            if self.debug >= 2:
                dump = subprocess.Popen(shlex.split("od -A x -t x2"),
                                        stdin=subprocess.PIPE,
                                        stdout=sys.stderr,
                                        stderr=sys.stderr)
                dump.communicate(input=self.data)
        finally:
            os.unlink(self.path)
            if self.made_dir:
                os.rmdir(self.dir)

class _OutboundTempFile(object):
    # Temporary file with same interface as _OutboundNamedPipe.
    def __init__(self, data, dir=None):
        self.data = data
        self.debug = False
        fd, self.path = tempfile.mkstemp(prefix="file.", dir=dir)
        os.write(fd, self.data)
        os.close(fd)
        if self.debug:
            msg = "<<wrote {0} bytes to tempfile {1}>>".format(len(self.data),
                                                               self.path)
            print >>sys.stderr, msg
        if self.debug >= 2:
            dump = subprocess.Popen(shlex.split("od -A x -t x2"),
                                    stdin=subprocess.PIPE,
                                    stdout=sys.stderr,
                                    stderr=sys.stderr)
            dump.communicate(input=self.data)

    def cleanup(self):
        if self.path:
            os.unlink(self.path)
            self.path = None

def closeall():
    global _allplots
    for ref in _allplots:
        plot = ref()
        if plot:
            plot.close()

