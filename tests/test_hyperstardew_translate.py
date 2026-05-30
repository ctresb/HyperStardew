from __future__ import annotations

import importlib.util
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO_ROOT / "tools" / "hyperstardew_tool.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("hyperstardew_tool_test", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


h = load_tool()


class RetryBackend(h.FreeGoogleTranslateBackend):
    def __init__(self):
        super().__init__(max_qps=1000, hop_retries=3, use_hop_cache=False)
        self.calls = 0

    def _translate_once(self, text: str, src: str, dst: str) -> str:
        self.calls += 1
        if self.calls == 1:
            raise h.TranslationRetryableError("temporary")
        return f"{text}-{dst}"


class AlwaysRetryBackend(h.FreeGoogleTranslateBackend):
    def __init__(self):
        super().__init__(max_qps=1000, hop_retries=2, use_hop_cache=False)

    def _translate_once(self, text: str, src: str, dst: str) -> str:
        raise h.TranslationRetryableError("still broken")


class FakeRescueBackend(h.TranslateBackend):
    name = "fake"

    def __init__(self):
        self.lock = threading.Lock()
        self.final_calls_by_source: dict[str, int] = {}

    def translate(self, text: str, src: str, dst: str) -> str:
        if "FAIL" in text:
            raise h.TranslationRetryableError("forced failure")
        if dst != "pt":
            return text
        with self.lock:
            self.final_calls_by_source[text] = self.final_calls_by_source.get(text, 0) + 1
            count = self.final_calls_by_source[text]
        return text if count == 1 else f"{text} torto"

    def metrics_dict(self):
        return {"backend": self.name, "requests": 0, "retries": 0, "failures": 0, "rate_limit_waits": 0}


class TranslateBackendTests(unittest.TestCase):
    def test_retry_backend_retries_then_succeeds(self):
        backend = RetryBackend()
        self.assertEqual(backend.translate("abc", "pt", "ja"), "abc-ja")
        self.assertEqual(backend.calls, 2)
        self.assertEqual(backend.metrics.to_dict()["retries"], 1)

    def test_retry_backend_fails_after_retry_budget(self):
        backend = AlwaysRetryBackend()
        with self.assertRaises(h.TranslationError):
            backend.translate("abc", "pt", "ja")

    def test_good_hyper_result_rejects_identity_and_near_original(self):
        self.assertTrue(h.is_good_hyper_result("Pizza", "pizza"))
        self.assertTrue(h.is_good_hyper_result("Bolo de Chocolate", "bolo de chocolate"))
        long_text = "Esta frase humana comprida precisa voltar claramente diferente no resultado final"
        self.assertFalse(h.is_good_hyper_result(long_text, long_text.lower()))
        self.assertTrue(h.is_good_hyper_result("Bolo de Chocolate", "A casa do açúcar torto"))

    def test_hypertranslate_candidate_keeps_25_hop_route(self):
        backend = RetryBackend()
        result = h.hypertranslate_candidate("abc", "normal", hops=25, backend=backend)
        self.assertEqual(result.hops, 25)
        self.assertEqual(len(result.route), 25)
        self.assertNotEqual(h.normalize_human(result.source), h.normalize_human(result.target))

    def test_translate_missing_super_rescues_identity(self):
        fake = FakeRescueBackend()
        with tempfile.TemporaryDirectory() as td, mock.patch.object(h, "CACHE_PATH", Path(td) / "cache.sqlite"), mock.patch.object(h, "FreeGoogleTranslateBackend", lambda: fake):
            translated, failures, records, metrics = h.translate_missing_super(["Esta frase comprida precisa ser muito diferente"])
        self.assertFalse(failures)
        self.assertEqual(translated["Esta frase comprida precisa ser muito diferente"], "Esta frase comprida precisa ser muito diferente torto")
        self.assertEqual(records[0]["route_kind"], "identity_rescue")
        self.assertEqual(metrics["backend"], "fake")

    def test_translate_missing_super_keeps_success_when_one_fragment_fails(self):
        fake = FakeRescueBackend()
        with tempfile.TemporaryDirectory() as td, mock.patch.object(h, "CACHE_PATH", Path(td) / "cache.sqlite"), mock.patch.object(h, "FreeGoogleTranslateBackend", lambda: fake):
            translated, failures, records, metrics = h.translate_missing_super(["FAIL", "Esta frase comprida precisa ser muito diferente"])
        self.assertIn("Esta frase comprida precisa ser muito diferente", translated)
        self.assertEqual(len(records), 1)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["piece"], "FAIL")

    def test_word_trigram_containment_counts_shared_word_blocks(self):
        source = "As árvores frutíferas crescem sazonalmente e produzem frutos deliciosos"
        target = "As árvores frutíferas crescem sazonalmente, então produzem frutos de vidro"
        self.assertGreaterEqual(h.word_ngram_containment(source, target, ngram=3), 0.30)
        shuffled = "Frutíferas as sazonalmente árvores frutos crescem deliciosos produzem"
        self.assertLess(h.word_ngram_containment(source, shuffled, ngram=3), 0.30)

    def test_similarity_candidate_requires_long_phrase_by_default(self):
        self.assertFalse(h.is_similarity_repair_candidate("Minha mãe me ensinou a receita."))
        self.assertTrue(h.is_similarity_repair_candidate("Sinto-me responsável pela saúde de toda a comunidade, e isso é meio estressante."))

    def test_similarity_render_preserves_dialogue_choice_structure(self):
        source = (
            'As árvores estão bonitas hoje, não acha?'
            '#$q 21/22/211132 Mon_old#Por que você resolveu trabalhar na fazenda?'
            '#$r 21 -5 Mon_21#Quero ganhar MUITO dinheiro.'
            '#$r 22 5 Mon_22#É mais "real" que morar na cidade.'
        )
        current = (
            'As árvores estão bonitas hoje, não acha?'
            '#$q 21/22/211132 Mon_old#Por que você resolveu trabalhar na fazenda?'
            '#$r 21 -5 Mon_21#Eu quero dinheiro ribombado.'
            '#$r 22 5 Mon_22#É mais "real" que morar na cidade.'
        )
        source_pieces = h.value_to_pieces("Characters/Dialogue/Leah.json", "Mon", source)
        action = {
            "action_type": "similarity_fragment_retranslate",
            "file": "Characters/Dialogue/Leah.json",
            "key": "Mon",
            "source_value": source,
            "threshold": 0.30,
            "ngram": 3,
            "fragments": [
                {
                    "fragment": 0,
                    "source_fragment": h.human_fragments(source_pieces)[0]["text"],
                    "target_fragment": h.human_fragments(h.value_to_pieces("Characters/Dialogue/Leah.json", "Mon", current))[0]["text"],
                }
            ],
        }
        new_value, failures = h.render_similarity_action_value(
            action,
            current,
            {action["fragments"][0]["source_fragment"]: "Hoje os troncos fazem desfile de guarda-chuva sem autorização"},
        )
        self.assertFalse(failures)
        self.assertIn("#$q 21/22/211132 Mon_old#", new_value)
        self.assertIn("#$r 21 -5 Mon_21#", new_value)
        self.assertIn("Eu quero dinheiro ribombado.", new_value)
        self.assertNotIn("As árvores estão bonitas hoje, não acha?", new_value)
        self.assertFalse(h.validate_similarity_repair_value("Characters/Dialogue/Leah.json", "Mon", source, new_value))

    def test_similarity_render_rejects_still_similar_translation(self):
        source = "As árvores frutíferas crescem sazonalmente e produzem frutos deliciosos."
        current = "As árvores frutíferas crescem sazonalmente e produzem frutos deliciosos."
        source_pieces = h.value_to_pieces("Strings/UI.json", "FruitHelp", source)
        action = {
            "action_type": "similarity_fragment_retranslate",
            "file": "Strings/UI.json",
            "key": "FruitHelp",
            "source_value": source,
            "threshold": 0.30,
            "ngram": 3,
            "fragments": [
                {
                    "fragment": 0,
                    "source_fragment": h.human_fragments(source_pieces)[0]["text"],
                    "target_fragment": current,
                }
            ],
        }
        _, failures = h.render_similarity_action_value(action, current, {source: current})
        self.assertEqual(failures[0]["reason"], "identity_translation")


if __name__ == "__main__":
    unittest.main()
