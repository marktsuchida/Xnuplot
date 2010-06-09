import contextlib
import formatter
import os
import pexpect
import re
import shutil
import sys
import tempfile
import threading
import warnings

class SpawnError(Exception): pass
class Timeout(Exception): pass
class CommunicationError(Exception): pass

class Gnuplot(object):

    gp_prompt = "gnuplot> "

    def __init__(self, command="/usr/bin/env gnuplot", persist=True):
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
        if self.gp_proc is not None and self.gp_proc.isalive():
                self("quit")
        self.terminate()

    def terminate(self):
        if self.gp_proc is not None:
            self.gp_proc.close(force=True)
            self.gp_proc = None
        if self.wk_dir:
            shutil.rmtree(self.wk_dir)
            self.wk_dir = None

    _placeholder_pattern = re.compile(r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}")
    _exitquit_pattern = re.compile(r"\s*(quit|exit)(\W|$)")
    def __call__(self, command, **kwargs):
        placeholders = list(self._placeholder_pattern.finditer(command))
        names = [p.group(1) for p in placeholders]
        for name in names:
            if name not in kwargs:
                raise ValueError(("content for file placeholder {{%s}} " +
                    "not provided" % name))
        if len(names) > len(set(names)):
            raise ValueError("duplicate file placeholder name(s)")

        # For each placeholder, create the pipe to send the data, and
        # substitute the name of the pipe for the placeholder.
        substituted_command = ""
        start_of_next_chunk = 0
        for placeholder in placeholders:
            name = placeholder.group(1)
            data = kwargs[name]
            pipe = OutboundNamedPipe(data, dir=self.wk_dir)
            if (self.debug):
                pipe.debug = True
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
            # When echoing is turned off (self.gp_proc.setecho(False)), Gnuplot
            # echoes the command. Since Gnuplot uses CRs to wrap lines, but the
            # whole echoed command is terminated by a CRLF, we can just throw
            # away everything up to the first CRLF.
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

    def async(self, command, **kwargs):
        raise UnimplementedError()

    def interact(self):
        # Debug mode (echoing) is a mere annoyance when in interactive mode.
        @contextlib.contextmanager
        def debug_turned_off():
            save_debug = self.debug
            self.debug = False
            yield
            self.debug = save_debug
        with debug_turned_off():
            print >>sys.stderr, "escape character is `^]'"
            self.gp_proc.interact()

        # The user could have quit Gnuplot.
        if not self.gp_proc.isalive():
            self.terminate()

    def set_timeout(self, seconds):
        self.gp_proc.timeout = seconds
    def get_timeout(self):
        return self.gp_proc.timeout
    timeout = property(get_timeout, set_timeout)

    def set_debug(self, debug=True):
        self.gp_proc.logfile_read = (sys.stderr if debug else None)
    def get_debug(self):
        return self.gp_proc.logfile_read is not None
    debug = property(get_debug, set_debug)

    @staticmethod
    def quote(filename):
        quoted =  "'" + filename.replace("\\", "\\\\").replace("'", "\\'") + "'"
        return quoted

class OutboundNamedPipe(threading.Thread):
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
        super(OutboundNamedPipe, self).__init__(name=self.path)
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
        finally:
            os.unlink(self.path)
            if self.made_dir:
                os.rmdir(self.dir)

