from __future__ import with_statement

import unittest


class FunctionalTest(unittest.TestCase):

    def setUp(self):
        import os
        import pkg_resources
        import shutil
        import tempfile
        self.tempdir = tmp = tempfile.mkdtemp('.karlservetests')
        etc = os.path.join(tmp, 'etc')
        os.mkdir(etc)
        ini = os.path.join(etc, 'karlserve.ini')
        shutil.copyfileobj(
            pkg_resources.resource_stream('karlserve.tests', 'karlserve.ini'),
            open(ini, 'wb'))
        instances = os.path.join(etc, 'instances.ini')
        with open(instances, 'w') as out:
            print >> out, "[instance:test1]"
            print >> out, "zodb_uri = file://%s/var/test1.db" % tmp
            print >> out, "[instance:test2]"
            print >> out, "zodb_uri = file://%s/var/test2.db" % tmp

        os.mkdir(os.path.join(tmp, 'var'))
        os.mkdir(os.path.join(tmp, 'mailout'))

        from webtest import TestApp
        from paste.deploy import loadapp
        self.app = TestApp(loadapp('config://%s' % ini))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tempdir)
        del self.app

    def test_login_and_make_a_blog_post(self):
        from webtest import Submit
        app = self.app
        response = app.get('/test1')
        while response.status_int > 300:
            response = response.follow()
        form = response.form
        form['login'] = 'admin'
        form['password'] = 'admin'
        response = form.submit()
        while response.status_int > 300:
            response = response.follow()
        response = response.click('BLOG')
        response = response.click('Add Blog')
        form = response.forms['save']
        form['title'] = 'Test blog entry.'
        form['text'] = 'My very interesting content'
        response = form.submit('submit')
        while response.status_int > 300:
            response = response.follow()
        body = str(response)
        self.assertTrue('Test blog entry.' in body)
        self.assertTrue('My very interesting content' in body)

