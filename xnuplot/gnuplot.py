import contextlib
import formatter
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
    """Raised when Gnuplot returns a (known) error."""

class RawGnuplot(object):
    """Low-level manager for communication with a Gnuplot subprocess."""

    gp_prompt = "gnuplot> "

    def __init__(self, command="/usr/bin/env gnuplot", persist=True):
        """Return a new Gnuplot object.

        Keyword Arguments:
        command - the command to use to invoke Gnuplot.
        persist - whether the plot window should stay open after this object
                  (and hence the Gnuplot subprocess) is destroyed.
        """
        if command is None:
            command = "/usr/bin/env gnuplot"
        self._debug = False
        self.wk_dir = tempfile.mkdtemp(prefix="xnuplot.")
        if persist:
            command += " -persist"
        try:
            self.gp_proc = pexpect.spawn(command)
            self.gp_proc.delaybeforesend = 0
        except:
            os.rmdir(self.wk_dir)
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
        if self.wk_dir:
            shutil.rmtree(self.wk_dir)
            self.wk_dir = None

    def isalive(self):
        return self.gp_proc is not None and self.gp_proc.isalive()

    _placeholder_pattern = re.compile(
            r"\{\{((?P<mode>file|pipe):)?(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\}\}")
    _exitquit_pattern = re.compile(r"\s*(quit|exit)(\W|$)")
    def __call__(self, command, **kwargs):
        """Send a command (or commands) to Gnuplot.

        If `command' contains newlines, __call__(command) is equivalent to
        script(command).

        If `command' is a single line, it can contain file placeholders of the
        form `{{foo}}'. These are substituted with temporary filenames for
        automatically created named pipes for passing data to Gnuplot. The data
        to pass must be given as a keyword argument with the same name (`foo'
        in this example).

        The placeholders can also have a mode-indicating prefix: {{file:foo}} or
        {{pipe:bar}}. The default is `pipe:'; `file:' causes the data to be
        written to a temporary file instead of a named pipe. The temporary file
        is not removed until the Gnuplot instance is deleted, so replot() can
        reuse the data.

        The user is responsible for ensuring that the format of the data is
        correct for the command to be sent.

        The return value is the tty output from Gnuplot (excluding the Gnuplot>
        prompt). This is often the empty string for successful commands.

        Example:
        gp = Gnuplot()
        gp("plot {{data}} notitle with linespoints", data="1 1\n2 2\n3 3")
        """
        mode = ("script" if "\n" in command else "line")
        placeholders = list(self._placeholder_pattern.finditer(command))
        if mode == "script":
            if len(placeholders):
                raise ValueError("multi-line command contains file " +
                                 "placeholder(s) (not allowed)")
            return self.script(command)
        names = [p.group("name") for p in placeholders]
        for name in names:
            if name not in kwargs:
                raise KeyError(("content for file placeholder {{%s}} " +
                    "not provided as keyword argument" % name))
        if len(names) > len(set(names)):
            raise ValueError("duplicate file placeholder name(s)")

        # For each placeholder, create the pipe to send the data, and
        # substitute the name of the pipe for the placeholder.
        substituted_command = ""
        start_of_next_chunk = 0
        for placeholder in placeholders:
            name = placeholder.group("name")
            mode = placeholder.group("mode")
            data = kwargs[name]

            pipeclass = (_OutboundTempFile if mode == "file"
                         else _OutboundNamedPipe)
            pipe = pipeclass(data, dir=self.wk_dir)
            pipe.debug = self.debug

            span_start, span_stop = placeholder.span(0)
            substituted_command += command[start_of_next_chunk:span_start]
            substituted_command += Gnuplot.quote(pipe.path)
            start_of_next_chunk = span_stop
        substituted_command += command[start_of_next_chunk:]
        command = substituted_command

        self.gp_proc.sendline(command)

        # The `quit' and `exit' commands require special handling.
        if self._exitquit_pattern.match(command):
            try:
                self.gp_proc.expect(pexpect.EOF)
            except pexpect.TIMEOUT:
                warnings.warn("timeout after quit command sent")
            self.terminate()
            return None

        try:
            # If Gnuplot is compiled with GNU readline support, we get the
            # echoed command string (this is true even if echoing is turned off
            # for the terminal). This string is wrapped with CRs, but it is
            # terminated by a CRLF. So discard everything up to the first CRLF.
            # This may need to be tweaked if Gnuplot was built without GNU
            # readline, built with Mac OS X's native non-GNU libreadline, or
            # built on other systems. Ideally, this would be done at build time
            # by some sort of automatic detection scheme.
            self.gp_proc.expect_exact("\r\n")
            self.gp_proc.expect_exact(self.gp_prompt)
        except pexpect.EOF:
            if self.gp_proc.isalive():
                warnings.warn("killing potentially zombie Gnuplot process")
            self.terminate()
            raise CommunicationError("Gnuplot died")
        except pexpect.TIMEOUT:
            if self.gp_proc.isalive():
                warnings.warn("killing potentially hanged Gnuplot process")
            self.terminate()
            raise CommunicationError("timeout")
        result = self.gp_proc.before
        return result

    def script(self, script):
        """Send a series of commands to Gnuplot.

        `script' is split at newlines and sent, one by one, to Gnuplot.
        A list of result strings is returned.
        """
        return [self(line) for line in script.split("\n")]

    def interact(self):
        """Interact directly with the Gnuplot subprocess.

        Handles control of the subprocess to the user.
        The interactive session can be terminated by typing CTRL-].
        """
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

    def set_timeout(self, seconds):
        self.gp_proc.timeout = seconds
    def get_timeout(self):
        return self.gp_proc.timeout
    timeout = property(get_timeout, set_timeout,
                       doc="Timeout (in seconds) for replies from Gnuplot.")

    def set_debug(self, debug=True):
        self._debug = debug
        self.gp_proc.logfile_read = (sys.stderr if debug else None)
    def get_debug(self):
        return self._debug
    debug = property(get_debug, set_debug,
                     doc="Echo communication with Gnuplot if true.")

    @staticmethod
    def quote(filename):
        """Return a quoted string for use as part of a Gnuplot command."""
        quoted =  "'" + filename.replace("\\", "\\\\").replace("'", "\\'") + "'"
        return quoted

class Gnuplot(RawGnuplot):
    """Manager for communication with a Gnuplot subprocess."""
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
                if isinstance(item, tuple):
                    item = PlotItem(*item)
                placeholder = "item%d" % i
                if hasattr(item, "use_real_file") and item.use_real_file:
                    item_str = "{{file:%s}}" % placeholder
                else:
                    item_str = "{{pipe:%s}} volatile" % placeholder
                if hasattr(item, "options") and item.options:
                    item_str = " ".join((item_str, item.options))
                item_strings.append(item_str)
                data_dict[placeholder] = item.data
        result = self(cmd + " " + ", ".join(item_strings), **data_dict)
        # Result should be the empty string if successful.
        if len(result):
            raise GnuplotError("`%s' returned error" % cmd, result)

    def plot(self, *items):
        """Issue a `plot' command with the given items.

        Each item can be a string, a PlotItem instance, or a tuple (which is
        used as the argument list to create a PlotItem instance).

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

class PlotItem(object):
    """Wrapper for an item in a Gnuplot `plot' or `splot' command."""
    def __init__(self, data, options=None, use_real_file=False):
        """Return a new PlotItem.

        Arguments:
        data          - The data to be sent to Gnuplot.
        options       - Datafile modifiers and plot options for the command
                        line (a string, such as "using 2:1 with linespoints").
        use_real_file - If true, a temporary file will be used to pass the data
                        to Gnuplot. This can be useful if you want replot() to
                        work, or if you want to send `binary matrix' data,
                        which doesn't work with named pipes. By default, a
                        named pipe is used.
        """
        self.data = data
        self.options = options
        self.use_real_file = use_real_file
    def __repr__(self):
        if self.options:
            return "<PlotItem: %d bytes %s>" % (len(self.data),
                                                repr(self.options))
        else:
            return "<PlotItem: %d bytes>" % len(self.data)

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

    def run(self):
        try:
            with open(self.path, "wb") as pipe:
                pipe.write(self.data)
            if self.debug:
                print >>sys.stderr, "<< wrote %d bytes to pipe %s >>" % \
                        (len(self.data), self.path)
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
            print >>sys.stderr, "<< wrote %d bytes to tempfile %s >>" % \
                    (len(self.data), self.path)
        if self.debug >= 2:
            dump = subprocess.Popen(shlex.split("od -A x -t x2"),
                                    stdin=subprocess.PIPE,
                                    stdout=sys.stderr,
                                    stderr=sys.stderr)
            dump.communicate(input=self.data)

    def unlink(self):
        # If this is not called, the user is responsible for removing the file
        # (by recursively removing the dir passed to __init__).
        os.unlink(self.path)

