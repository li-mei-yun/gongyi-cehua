"""Render torque versus angle, preserving acquisition order (Matplotlib).

Use C:/dlcv/python.exe on this host: the bundled runtime lacks Matplotlib.
"""
import base64
from io import BytesIO
import os
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', str(Path(__file__).resolve().parent / '.mpl-cache'))
import matplotlib
matplotlib.use('Agg')
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties

FONT = FontProperties(fname='C:/Windows/Fonts/msyh.ttc')


def figure_for(task):
    series = task['data']['series']
    angle, torque = series['angle_deg'], series['torque_nm']
    if len(angle) != len(torque) or len(angle) < 2:
        raise ValueError('Angle and torque must be paired')
    fig = Figure(figsize=(12, 8.4), dpi=100)
    ax = fig.add_subplot(111)
    # Do not sort, aggregate duplicate angles, smooth, or decimate the path.
    line, = ax.plot(angle, torque, color='#1f77b4', linewidth=1.6)
    if list(line.get_xdata()) != angle or list(line.get_ydata()) != torque:
        raise ValueError('Plot data differs from source series')
    ax.set_title(f"Result ID: {task['data']['curve_id']}", fontsize=18, pad=16)
    ax.set_xlabel('角度（度）', fontproperties=FONT, fontsize=15, labelpad=10)
    ax.set_ylabel('扭矩（N·m）', fontproperties=FONT, fontsize=15, labelpad=10)
    ax.grid(True, linestyle='--', color='#cccccc', linewidth=0.8)
    ax.tick_params(labelsize=11)
    ax.margins(x=0.035, y=0.07)
    fig.subplots_adjust(left=0.10, right=0.975, bottom=0.12, top=0.90)
    return fig


def render_svg(task):
    with matplotlib.rc_context({'path.simplify': False, 'svg.hashsalt': 'tightening-xy-v1', 'axes.unicode_minus': False}):
        fig = figure_for(task)
        stream = BytesIO()
        fig.savefig(stream, format='svg', metadata={'Date': None})
        fig.clear()
        return stream.getvalue()


def data_uri(task):
    return 'data:image/svg+xml;base64,' + base64.b64encode(render_svg(task)).decode('ascii')


if __name__ == '__main__':
    import json
    root = Path(__file__).resolve().parent
    task = json.loads((root.parent / 'curve-import-3918223/tasks_3918223.json').read_text(encoding='utf-8'))[0]
    output = root / 'xy-preview'
    output.mkdir(exist_ok=True)
    (output / '3918223.svg').write_bytes(render_svg(task))
    fig = figure_for(task)
    fig.savefig(output / '3918223.png', dpi=100)
    fig.clear()
    task['data']['angle_torque_plot'] = data_uri(task)
    (output / 'sample.json').write_text(json.dumps(task, ensure_ascii=False), encoding='utf-8')
    print(f'Preview saved; {len(task["data"]["series"]["angle_deg"])} paired points preserved.')
