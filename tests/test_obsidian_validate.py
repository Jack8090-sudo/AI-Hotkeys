"""obsidian_todo safety checks (I4): structure, tasks, links, tags, truncation, normalisation."""

import unittest

from tests.support import FIXTURES, AppTree

GOLDEN = (FIXTURES / "todo" / "golden_ok.md").read_text(encoding="utf-8")


class ObsidianValidateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = AppTree()
        cls.ot = cls.tree.load_action("obsidian_todo")

    @classmethod
    def tearDownClass(cls):
        cls.tree.close()

    def errors(self, new, original=GOLDEN):
        return self.ot.validate(original, new)

    def test_identical_file_passes(self):
        self.assertEqual(self.errors(GOLDEN), [])
        self.assertEqual(self.ot.check_structure(GOLDEN), [])

    def test_reordered_task_inside_rules_passes(self):
        lines = GOLDEN.split("\n")
        i = lines.index("- [ ] Sistema di clan")
        j = lines.index("- [ ] Modalità classificata con stagioni")
        lines[i], lines[j] = lines[j], lines[i]
        self.assertEqual(self.errors("\n".join(lines)), [])

    def test_missing_or_misordered_level_fails(self):
        self.assertTrue(self.ot.check_structure(GOLDEN.replace("# 🔴", "# rosso")))
        swapped = GOLDEN.replace("# 🟢", "# TMP").replace("# 🟡", "# 🟢").replace("# TMP", "# 🟡")
        self.assertIn("levels are not in order 🟢 → 🟡 → 🔴", self.ot.check_structure(swapped))

    def test_missing_category_fails(self):
        self.assertTrue(self.ot.check_structure(GOLDEN.replace("### ⚙️ Game Design", "### Design", 1)))

    def test_idee_instead_of_idea_fails(self):
        self.assertTrue(any("Idee" in e for e in self.errors(GOLDEN.replace("### 💡 Idea", "### 💡 Idee", 1))))

    def test_lost_task_fails(self):
        self.assertTrue(self.errors(GOLDEN.replace("- [ ] Sistema di clan\n", "")))

    def test_changed_checkbox_fails(self):
        self.assertTrue(self.errors(GOLDEN.replace("- [ ] Sistema di clan", "- [x] Sistema di clan")))

    def test_lost_url_wikilink_image_tag_fail(self):
        for old, new in (("https://example.com/lag-report", "https://example.com/other"),
                         ("[[Shop UI]]", "[[Shop]]"),
                         ("![[pet-sketch.png]]", ""),
                         ("#economia", "economia")):
            with self.subTest(removed=old):
                self.assertTrue(self.errors(GOLDEN.replace(old, new)))

    def test_truncated_result_fails(self):
        cut = GOLDEN[: int(len(GOLDEN) * 0.5)]
        self.assertTrue(any("too short" in e for e in self.errors(cut)))

    def test_tags_inside_code_are_ignored(self):
        original = GOLDEN.replace("Sistema di clan", "Sistema di clan `#notatag`")
        new = GOLDEN.replace("Sistema di clan", "Sistema di clan `codice`")
        self.assertEqual(self.errors(new, original), [])

    def test_task_states(self):
        counts = self.ot.task_states("- [ ] a\n- [x] b\n- [X] c\n1. [ ] d\n* [-] e\n")
        self.assertEqual(counts, {" ": 2, "x": 2, "-": 1})

    def test_normalize(self):
        raw = ("<think>ragiono</think>\n```markdown\n## 🟢\n\n## 🐛 Bugs\n\n#### ⚙ Game Design\n\n"
               "### 💡 Idee\n```")
        self.assertEqual(self.ot.normalize(raw), "# 🟢\n\n### 🐛 Bug\n\n### ⚙️ Game Design\n\n### 💡 Idea\n")
        self.assertEqual(self.ot.normalize(GOLDEN.replace("\n", "\r\n")), GOLDEN.strip() + "\n")

    def test_translation_and_spelling_fixes_are_accepted(self):
        original = GOLDEN.replace("Sistema di clan", "Add a pet that follows the player")
        new = GOLDEN.replace("Sistema di clan", "Aggiungere un pet che segue il giocatore")
        self.assertEqual(self.errors(new, original), [])

    def test_preserved_frontmatter_passes(self):
        original = "---\ntags: [todo]\n---\n\n" + GOLDEN
        self.assertEqual(self.errors(original, original), [])

    def test_dropped_paragraph_fails(self):
        original = GOLDEN.replace("### 🐛 Bug\n\n- [ ] Lag", "### 🐛 Bug\n\nNota: priorità alta questa settimana.\n\n- [ ] Lag", 1)
        self.assertTrue(any("paragraph" in e for e in self.errors(GOLDEN, original)))

    # ---- C14 (fixed in S5) ----

    def test_C14_dropped_frontmatter_fails(self):
        """C14: content before the first level (frontmatter) can disappear unnoticed."""
        original = "---\ntags: [todo]\nupdated: 2026-10-01\n---\n\n" + GOLDEN
        self.assertTrue(self.errors(GOLDEN, original))

    def test_C14_replaced_task_text_fails(self):
        """C14: a task can be rewritten into something unrelated with the same checkbox."""
        self.assertTrue(self.errors(GOLDEN.replace("Sistema di clan", "Comprare il latte")))


if __name__ == "__main__":
    unittest.main()
