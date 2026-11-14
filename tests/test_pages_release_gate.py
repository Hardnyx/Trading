"""Publication decisions after the fast CI validated a commit."""
import io
import json
import unittest

from scripts.pages_release_gate import DEPLOY_PATHS, decide, served_commit

HEAD, SERVED, TIP = "a" * 40, "b" * 40, "c" * 40


def fake_git(known=True, newer=False, changed="dist/index.html", diff_code=0,
             later=""):
    def run(*args):
        if args[0] == "cat-file":
            return (0 if known else 1), ""
        if args[0] == "merge-base":
            return (0 if newer else 1), ""
        if args[0] == "diff":
            assert args[-len(DEPLOY_PATHS):] == DEPLOY_PATHS
            if args[2:4] == (HEAD, TIP):
                return 0, later
            assert args[2:4] == (SERVED, HEAD)
            return diff_code, changed
        raise AssertionError(args)
    return run


class PagesReleaseGateTests(unittest.TestCase):
    def test_published_changes_deploy_and_others_do_not(self):
        self.assertTrue(decide(HEAD, HEAD, SERVED, fake_git())[0])
        self.assertFalse(decide(HEAD, HEAD, SERVED, fake_git(changed=""))[0])
        self.assertFalse(decide(HEAD, None, HEAD, fake_git())[0])

    def test_cancelled_deployment_is_caught_up_by_the_next_run(self):
        # The served commit is older than both pushes, so the diff spans the
        # dist change of a cancelled run even if the latest push did not touch it.
        deploy, reason = decide(HEAD, HEAD, SERVED, fake_git(changed="dist/a.js\ndist/b.css"))
        self.assertTrue(deploy)
        self.assertIn("2 published", reason)

    def test_never_overwrites_newer_main_or_newer_site(self):
        self.assertFalse(decide(HEAD, TIP, SERVED, fake_git(later="dist/data/market.json"))[0])
        self.assertFalse(decide(HEAD, HEAD, SERVED, fake_git(newer=True))[0])

    def test_later_unpublished_commit_does_not_block_this_release(self):
        # A later docs-only or [skip ci] commit triggers no deployment of its own.
        self.assertTrue(decide(HEAD, TIP, SERVED, fake_git(later=""))[0])
        self.assertFalse(decide(HEAD, TIP, SERVED, fake_git(later="", changed=""))[0])

    def test_doubt_resolves_towards_publishing(self):
        self.assertTrue(decide(HEAD, HEAD, None, fake_git(changed=""))[0])
        self.assertTrue(decide(HEAD, HEAD, SERVED, fake_git(known=False, changed=""))[0])
        self.assertTrue(decide(HEAD, HEAD, SERVED, fake_git(changed="", diff_code=128))[0])

    def test_served_commit_parsing_rejects_malformed_metadata(self):
        def opener(payload):
            return lambda url, timeout: io.BytesIO(payload)
        self.assertEqual(served_commit("https://x/", "n", opener=opener(json.dumps({"commit": SERVED}).encode())), SERVED)
        for payload in (b"{}", b"not json", json.dumps({"commit": "HEAD"}).encode(),
                        json.dumps(["x"]).encode()):
            self.assertIsNone(served_commit("https://x", opener=opener(payload)))

        def broken(url, timeout):
            raise OSError("offline")
        self.assertIsNone(served_commit("https://x", opener=broken))


if __name__ == "__main__":
    unittest.main()
