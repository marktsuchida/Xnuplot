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

class CommunicationError(RuntimeError):
    """Raised when communication with Gnuplot subprocess failed."""

class GnuplotError(RuntimeError):
    """Raised when Gnuplot (is known to have) responded with an error."""

class RawGnuplot(object):
    """Low-level manager for communication with a Gnuplot subprocess."""

    gp_prompt = "gnuplot> "

    def __init__(self, command="gnuplot", persist=False, tempdir=None):
        """Return a new Gnuplot object.

        Keyword Arguments:
        command - The command to use to invoke Gnuplot.
        persist - Whether the plot window should stay open after this object
                  (and hence the Gnuplot subprocess) is destroyed.
        tempdir - Directory to use for temporary data. A new directory is
                  created within the given directory, whose name is stored in
                  self.tempdir.
        """
        self._debug = False
        self.tempdir = tempfile.mkdtemp(prefix="xnuplot.", dir=tempdir)
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

    def _send_one_command(self, command, **data):
        # Do the acutal work for __call__().
        with self._placeholders_substituted(command, **data) as command:
            self.gp_proc.sendline(command)
            try:
                # If Gnuplot is compiled with GNU readline support, we get the
                # echoed command string (this is true even if echoing is turned
                # off for the terminal). This string is wrapped with CRs, but
                # it is terminated by a CRLF. So discard everything up to the
                # first CRLF. This may need to be tweaked if Gnuplot was built
                # without GNU readline, built with Mac OS X's native non-GNU
                # libedit, or built on other systems. Ideally, this would be
                # done at build time by some sort of automatic detection
                # scheme.
                self.gp_proc.expect_exact("\r\n")
                self.gp_proc.expect_exact(self.gp_prompt)
            except pexpect.EOF:
                if self.gp_proc.isalive():
                    warnings.warn("killing potentially zombie Gnuplot process")
                self.terminate()
                if re.match(r"\s*(quit|exit)(\W|$)", command):
                    return None
                else:
                    raise CommunicationError("Gnuplot died")
            except pexpect.TIMEOUT:
                if self.gp_proc.isalive():
                    warnings.warn("killing potentially hanged Gnuplot process")
                self.terminate()
                raise CommunicationError("timeout")
        result = self.gp_proc.before
        return result.replace("\r\n", "\n")

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
                # XXX Check whether the switches to `od' differ for the GNU
                # version (the ones below work for the BSD version).
                # (Also below in _OutboundTempFile.)
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
            # XXX See above (in _OutboundNamedPipe).
            dump = subprocess.Popen(shlex.split("od -A x -t x2"),
                                    stdin=subprocess.PIPE,
                                    stdout=sys.stderr,
                                    stderr=sys.stderr)
            dump.communicate(input=self.data)

    def cleanup(self):
        if self.path:
            os.unlink(self.path)
            self.path = None

