from tests.coprs_test_case import CoprsTestCase

class TestAdminLogin(CoprsTestCase):
    # TODO: test on something better then page title - maybe see rendered templates?
    text_to_check = 'Coprs - Admin'
    def test_nonadmin_cant_login(self, f_users, f_db):
        with self.tc as c:
            with c.session_transaction() as s:
                s['openid'] = self.u2.openid_name

        r = c.get('/admin/', follow_redirects=True)
        assert self.text_to_check not in r.data

    def test_admin_can_login(self, f_users, f_db):
        with self.tc as c:
            with c.session_transaction() as s:
                s['openid'] = self.u1.openid_name

        r = c.get('/admin/', follow_redirects=True)
        assert self.text_to_check in r.data