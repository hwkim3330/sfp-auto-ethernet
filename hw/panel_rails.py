"""KiKit framing plugin: rails on top, bottom and the RIGHT side only.

The left edge of the panel is where every board's gold fingers end, and it has
to stay a clean, straight board edge: JLC bevels it, and a bevel cannot run
through a rail. KiKit's own framings are both rails (top/bottom or left/right)
or a full frame, so this one builds the three sides it needs.

arg: "rail_mm,space_mm,min_width_mm,min_height_mm"
     rails grow until the panel reaches min width x min height (JLC standard
     PCBA wants 70 x 70; gold fingers need >= 50 mm per side)
"""
from shapely.geometry import box

from kikit.plugin import FramingPlugin
from kikit.panelize_ui_impl import polygonToSubstrate
from kikit.units import mm


class ThreeSideRails(FramingPlugin):
    def _params(self):
        w, s, mw, mh = (float(v) for v in self.userArg.split(','))
        return w * mm, s * mm, mw * mm, mh * mm

    def _rails(self, minx, miny, maxx, maxy):
        w, s, mw, mh = self._params()
        wtb = max(w, (mh - (maxy - miny)) / 2 - s)
        wr = max(w, mw - (maxx - minx) - s)
        right_x0 = maxx + s
        right_x1 = right_x0 + wr
        top = box(minx, maxy + s, right_x1, maxy + s + wtb)
        bottom = box(minx, miny - s - wtb, right_x1, miny - s)
        right = box(right_x0, miny - s - wtb, right_x1, maxy + s + wtb)
        return top, bottom, right

    def buildFraming(self, panel):
        minx, miny, maxx, maxy = panel.boardsBBox()
        for r in self._rails(minx, miny, maxx, maxy):
            panel.appendSubstrate(r)
        return []

    def buildDummyFramingSubstrates(self, substrates):
        minx = min(s.bounds()[0] for s in substrates)
        miny = min(s.bounds()[1] for s in substrates)
        maxx = max(s.bounds()[2] for s in substrates)
        maxy = max(s.bounds()[3] for s in substrates)
        return [polygonToSubstrate(r) for r in self._rails(minx, miny, maxx, maxy)]
