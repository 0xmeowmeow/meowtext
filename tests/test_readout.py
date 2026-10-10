"""A readout file turns a source into numbers and a panel."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from meowtext.readout import EXAMPLE, load_plot, load_readout, render_plot, render_readout, sample
from meowtext.readout import Readout


class ReadoutTests(unittest.TestCase):
    def test_the_example_file_maps_its_range(self) -> None:
        readout = load_readout(EXAMPLE)
        values = sample(readout)
        self.assertEqual(values, [0.12, 0.4, 0.75, 0.9, 0.55])
        self.assertEqual(render_readout(readout, 80, 40).size, (80, 40))

    def test_count_keeps_the_latest_values(self) -> None:
        readout = Readout("tail", "cells", "memory:series", "numbers", None, 0, 10, 2)
        self.assertEqual(sample(readout, {"series": [1, 2, 9]}), [0.2, 0.9])

    def test_json_field_and_script_and_a_missing_file(self) -> None:
        payload = json.dumps({"sensors": {"temp": [10, 30]}})
        found = Readout("temp", "gauge", "memory:body", "json", "sensors.temp", 0, 40, 8)
        self.assertEqual(sample(found, {"body": payload}), [0.25, 0.75])
        script = Readout(
            "once",
            "gauge",
            f"script:{sys.executable} -c \"print(25)\"",
            "numbers",
            None,
            0,
            50,
            1,
        )
        self.assertEqual(sample(script), [0.5])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gone.json"
            path.write_text(json.dumps({"source": "file:missing.txt", "style": "gauge", "format": "lines", "range": [0, 1]}), encoding="utf-8")
            image = render_readout(load_readout(path), 80, 30)
        self.assertEqual(image.size, (80, 30))

    def test_amber_plot_is_two_point_readouts_inside_a_ticked_frame(self) -> None:
        plot = load_plot(EXAMPLE.parent / "amber-plot.json")
        self.assertEqual(plot.border, "ticks")
        self.assertTrue(plot.perspective)
        self.assertEqual(plot.x_axis, "R-AXIS")
        self.assertEqual([item.layout for item in plot.readouts], ["curves", "columns"])
        image = render_plot(plot, 240, 160)
        self.assertEqual(image.size, (240, 160))
        self.assertTrue(any(pixel[0] > pixel[2] + 20 for pixel in image.getdata()))
        flat = render_plot(type(plot)(plot.name, plot.ink, "none", plot.readouts, "none", False), 240, 160)
        self.assertNotEqual(image.tobytes()[::50], flat.tobytes()[::50])


if __name__ == "__main__":
    unittest.main()
