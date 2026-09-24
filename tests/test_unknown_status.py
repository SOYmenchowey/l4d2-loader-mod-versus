import unittest

import l4d2_sidebar as sidebar
import l4d2_ui as ui


class UnknownStatusTests(unittest.TestCase):
    def snapshot(self):
        return dict(game_found=True, game_running=None, gameinfo_writable=True,
                    gameinfo_exists=True, workshop_exists=True, pending_cleanup_count=0)

    def test_report_does_not_claim_game_is_closed_when_check_failed(self):
        snapshot = self.snapshot()
        self.assertIn('Juego abierto: Desconocido', ui.format_diagnostic_report(snapshot))
        self.assertTrue(any('comprobar' in warning for warning in ui.diagnostic_warnings(snapshot)))

    def test_sidebar_unknown_process_status_is_not_green_ok(self):
        row = sidebar.build_health_card(self.snapshot()).content.controls[2]
        self.assertEqual(row.controls[-1].value, 'Desconocido')
        self.assertEqual(row.controls[-1].color, sidebar.AMBER)


if __name__ == '__main__':
    unittest.main()
