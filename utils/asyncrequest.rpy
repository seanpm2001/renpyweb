# HTTP Requests that work in both native Ren'Py and RenPyWeb

# Copyright (C) 2019  Sylvain Beucler

# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

# Ren'Py doesn't ship with certificates authorities, so for native
# Ren'Py add your server certificate chain in 'yourgame/game/ca.pem'
# (not in a .rpa, urllib2 wants an existing filename)
# (for RenPyWeb, the browser's certificates are used)
# 
# Requests do not rollback (we can't rollback the remote server!) but
# the user can rollback the game, so beware that the user may send a
# request multiple times

init python:
    import os

    if renpy.variant('web'):

        import emscripten, binascii, json
        class AsyncRequest:
            def __init__(self):
                while True:
                    self.filename = '/tmp/req-' + binascii.hexlify(os.urandom(8))
                    if not os.path.exists(self.filename):
                        break
                self.response = ''
                self.finished = False
            def send(self, endpoint, headers={}, data=None):

                emscripten.run_script(r'''
                  (function () {
                    try {
                      var filename = %s;
                      var url = %s;
                      var headers = %s;
                      var data = %s;
                      console.log("data", data);

                      var xhr = new XMLHttpRequest();
                      var method = 'GET';
                      if (data !== null) {
                        method = 'POST';
                      }
                      xhr.open(method, url);

                      if (data !== null) {
                        xhr.setRequestHeader('Content-Type',
                          'application/x-www-form-urlencoded');
                      }
                      Object.keys(headers).forEach(function(key) {
                        xhr.setRequestHeader(key, headers[key]);
                      });
                      
                      xhr.onerror = function(event) {
                          FS.writeFile(filename,
                            JSON.stringify({
                              'success': false,
                              'status': event.target.status
                            })
                          );
                      }
                      xhr.onload = function(event) {
                        if (this.status==200||this.status==304||this.status==206||this.status==0&&this.response) {
                          FS.writeFile(filename,
                            JSON.stringify({
                              'success': true,
                              'status': this.status,
                              'responseText': this.responseText
                            })
                          );
                        } else {
                          FS.writeFile(filename,
                            JSON.stringify({
                              'success': false,
                              'status': this.status,
                              'statusText': this.statusText,
                              'responseText': this.responseText
                            })
                          );
                        }
                      }

                      xhr.timeout = 10000;
                      xhr.ontimeout = function(event) {
                          FS.writeFile(filename,
                            JSON.stringify({
                              'success': false,
                              'status': event.target.status,
                              'statusText': 'timeout'
                            })
                          );
                      }

                      xhr.send(data);
                    } catch (exception) {
                      console.log(exception);
                      FS.writeFile(filename,
                        JSON.stringify({
                          'success': false,
                          'exception': exception,
                        })
                      );
                    }
                  })();
                ''' % (json.dumps(self.filename), json.dumps(endpoint),
                       json.dumps(headers), json.dumps(data)))
                # new TextDecoder('utf-8').decode(FS.readFile('/tmp/t'))

            def isAlive(self):
                return not (self.finished or os.path.exists(self.filename))
            def readfs(self):
                if os.path.exists(self.filename):
                    try:
                        self.response = json.loads(open(self.filename).read())
                    except ValueError, e:
                        self.response = {'success': False, 'exception': str(e) }
                    os.unlink(self.filename)
                    self.done = True
            def getError(self):
                self.readfs()
                if self.response and not self.response.get('success', True):
                    if self.response.get('exception', None):
                        return 'Exception: ' + self.response.get['exception']
                    elif self.response.get('status', None):
                        if self.response.get('statusText', None):
                            return self.response['statusText'] + '(' + str(self.response['status']) + ')'
                        else:
                            return str(self.response['status'])
                return None
            def getResponse(self):
                self.readfs()
                if self.response and self.response.get('success', False):
                    return self.response['responseText']
                return None

    else:

        import threading, urllib2, httplib
        import time
        class AsyncRequest:
            def __init__(self):
                self.thread = None
                self.response = None
                self.error = None
            def __getstate__(self):
                self.thread = None
                return self.__dict__
            def send(self, endpoint, headers={}, data=None):
                req = urllib2.Request(endpoint, headers=headers, data=data)
                def thread_main():
                    cafile = os.path.join(renpy.config.gamedir, 'ca.pem')
                    if not os.path.exists(cafile): cafile = None
                    try:
                        r = urllib2.urlopen(req, cafile=cafile, timeout=10)
                        self.response = r.read()
                    except urllib2.URLError, e:
                        self.error = str(e.reason)
                    except httplib.HTTPException, e:
                        self.error = 'HTTPException'
                    except Exception, e:
                        self.error = 'Error: ' + str(e)
                # self.thread = threading.Thread(target=lambda:time.sleep(1))
                self.thread = threading.Thread(target=thread_main)
                self.thread.start()
            def isAlive(self):
                return self.thread and self.thread.isAlive()
                #if self.thread:
                #    if self.thread.isAlive():
                #        return True
                #    else:
                #        self.thread = None
                #return False
            def getError(self):
                return self.error
            def getResponse(self):
                return self.response