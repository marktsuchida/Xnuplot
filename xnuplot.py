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

class SpawnError(RuntimeError):
    """Raised upon failure to initiate communication with Gnuplot subprocess."""

class CommunicationError(RuntimeError):
    """Raised when communication with Gnuplot subprocess failed."""

class Gnuplot(object):
    """Manager for communication with a Gnuplot subprocess."""

    gp_prompt = "gnuplot> "

    def __init__(self, command="/usr/bin/env gnuplot", persist=True):
        """Return a new Gnuplot object.

        Keyword Arguments:
        command - the command to use to invoke Gnuplot.
        persist - whether the plot window should stay open after this object
                  (and hence the Gnuplot subprocess) is destroyed.
        """
        self._debug = False
        self.wk_dir = tempfile.mkdtemp(prefix="xnuplot.")
        if persist:
            command += " -persist"
        try:
            self.gp_proc = pexpect.spawn(command)
            self.gp_proc.delaybeforesend = 0
        except Exception as e:
            os.rmdir(self.wk_dir)
            raise SpawnError(str(e))
        except BaseException:
            os.rmdir(self.wk_dir)
            raise
        try:
            self.gp_proc.expect_exact(self.gp_prompt)
        except pexpect.EOF:
            if self.gp_proc.isalive():
                warnings.warn("killing potentially zombie Gnuplot process")
            self.gp_proc.close(force=True)
            os.rmdir(self.wk_dir)
            raise SpawnError("Gnuplot died before first prompt")
        except pexpect.TIMEOUT:
            self.gp_proc.close(force=True)
            os.rmdir(self.wk_dir)
            raise SpawnError("timeout")
        except BaseException:
            os.rmdir(self.wk_dir)
            raise

    def __enter__(self):
        return self
    def __exit__(self, type, value, traceback):
        self.close()
    def __del__(self):
        self.close()

    def close(self):
        """Close the Gnuplot subprocess and remove all temporary files."""
        if self.gp_proc is not None and self.gp_proc.isalive():
            self("quit")
        else:
            self.terminate()

    def terminate(self):
        """Force-quit the Gnuplot subprocess and remove all temporary files."""
        if self.gp_proc is not None:
            self.gp_proc.close(force=True)
            self.gp_proc = None
        if self.wk_dir:
            shutil.rmtree(self.wk_dir)
            self.wk_dir = None

    _placeholder_pattern = re.compile(r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}")
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
        names = [p.group(1) for p in placeholders]
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
            name = placeholder.group(1)
            data = kwargs[name]
            pipe = _OutboundNamedPipe(data, dir=self.wk_dir)
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
            # At least on Mac OS X, I get the command echoed back whether or
            # not I have echoing turned on for the pty. And the echoed-back
            # command is wrapped with CRs but terminated with a CRLF. So
            # discard everything up to the first CRLF.
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

    def _plot(self, cmd, *items):
        # Common implementation for plot() and splot().
        item_strings = []
        data_dict = {}
        for i, item in enumerate(items):
            if isinstance(item, basestring):
                item_strings.append(item)
            else:
                if len(item) != 2 or not isinstance(item[1], basestring):
                    raise ValueError("plot item must be a string or " +
                                     "a (data, string) pair")
                placeholder = "pipe%d" % i
                item_strings.append("{{%s}} volatile %s" % (placeholder,
                                                            item[1]))
                data_dict[placeholder] = item[0]
        self(cmd + " " + ", ".join(item_strings), **data_dict)

    def plot(self, *items):
        """Issue a `plot' command with the given items.

        Each argument (in `items') may be either a string, or a pair
        (data, string). In the latter case, `data' will be piped to Gnuplot
        (appearing to Gnuplot as a datafile), and `string' should not contain
        a function or filename.

        See also: splot()

        Example:
        Gnuplot().plot("sin(x) notitle", "'some_file.dat' with lp",
                       (some_data, "binary array=(512,512) with image"))
        """
        self._plot("plot", *items)

    def splot(self, *items):
        """Issue an `splot' command with the given items.

        Each argument (in `items') may be either a string, or a pair
        (data, string). In the latter case, `data' will be piped to Gnuplot
        (appearing to Gnuplot as a datafile), and `string' should not contain
        a function or filename.

        See also: plot()
        """
        self._plot("splot", *items)

    def replot(self, *items):
        """Issue a `replot' command with the given items.

        Each argument (in `items') may be either a string, or a pair
        (data, string). In the latter case, `data' will be piped to Gnuplot
        (appearing to Gnuplot as a datafile), and `string' should not contain
        a function or filename.

        Note that `replot' does not work when the previous plot was made by
        passing data to Gnuplot.

        See also: plot(), splot()
        """
        self._plot("replot", *items)

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

