import copy
import unittest
from unittest.mock import Mock, patch

import app


class HobbingFixtureTests(unittest.TestCase):
    def setUp(self):
        self.config = copy.deepcopy(app.load_config())
        self.scene = app.find_scene(self.config, "hobbing_fixture")
        self.scene["api_key"] = "app-test-only"
        self.client = app.app.test_client()
        self.values = {
            "workpiece_diameter": "120", "module": "2.5",
            "teeth_count": "48", "bore_diameter": "30",
            "workpiece_thickness": "25", "support_diameter_min": "35",
            "support_diameter_max": "60",
        }

    def test_fallback_fields(self):
        self.scene["api_key"] = ""
        with patch("app.load_config", return_value=self.config):
            response = self.client.get("/api/scenes/hobbing_fixture/form")
        self.assertEqual(response.status_code, 200)
        fields = response.get_json()["fields"]
        self.assertEqual({f["variable"] for f in fields}, set(self.values))
        self.assertTrue(all(f["type"] == "number" and f["required"] for f in fields))

    def test_required_and_number_validation(self):
        fields = app.normalize_local_fields(self.scene["fields"])
        for key in self.values:
            values = dict(self.values)
            values.pop(key)
            with self.assertRaises(app.AppError):
                app.validate_inputs(fields, values)
        for bad in ("abc", "nan", "inf"):
            with self.assertRaises(app.AppError):
                app.validate_inputs(fields, {**self.values, "module": bad})
        values = app.validate_inputs(fields, self.values)
        self.assertEqual(values["module"], 2.5)
        self.assertEqual(values["teeth_count"], 48)

    def test_both_run_routes(self):
        mock_response = Mock(ok=True, status_code=200)
        mock_response.json.return_value = {
            "data": {"status": "succeeded", "outputs": {"result": "# Fixture report"}}
        }
        form = {"fields": app.normalize_local_fields(self.scene["fields"])}
        with patch("app.load_config", return_value=self.config), patch(
            "app.fetch_scene_form", return_value=form
        ), patch("app.requests.post", return_value=mock_response) as post:
            for route in (
                "/api/scenes/hobbing_fixture/run",
                "/api/modules/quick_change_fixture/run",
            ):
                response = self.client.post(route, json={"inputs": self.values})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json()["output_text"], "# Fixture report")
                self.assertEqual(post.call_args.kwargs["json"]["inputs"]["module"], 2.5)
                self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer app-test-only")
            before = post.call_count
            response = self.client.post(
                "/api/modules/quick_change_fixture/run",
                json={"scene_id": "guangkong", "inputs": self.values},
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(post.call_count, before)


if __name__ == "__main__":
    unittest.main()
