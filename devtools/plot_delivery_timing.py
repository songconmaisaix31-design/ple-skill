"""Plot the two observed events for each independently scored P–U file pair."""
import csv
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

FOLDER = Path(__file__).resolve().parents[1] / 'docs/experiments/delivery-timing-2026-11-24'


def main():
    with (FOLDER / 'trials.csv').open(newline='') as source:
        rows = list(csv.DictReader(source))
    candidates = [row for row in rows if row['arm'] == 'native-actionable']
    baseline = [row for row in rows if row['arm'] == 'native-feedback']
    scored = [row for row in rows if float(row['score_at_395']) == 1]
    if len(candidates) != 18 or len(baseline) != 18 or any(row not in candidates for row in scored):
        raise ValueError('expected the archived P–U paired experiment')

    ink, accent, muted = '#182d3d', '#167a78', '#496170'
    fig, ax = plt.subplots(figsize=(8.1, 5.4))
    fig.subplots_adjust(left=.24, right=.95, top=.76, bottom=.18)
    fig.text(.055, .93, 'When Gemma’s repairs produced both files', color=ink,
             fontsize=20, weight='bold')
    handles = [Line2D([], [], marker='o', linestyle='', markerfacecolor=fill,
                      markeredgecolor=accent, markeredgewidth=1.6, markersize=6.5, label=label)
               for fill, label in [('white', 'First patch accepted'), (accent, 'File-writing program returned')]]
    fig.legend(handles=handles, loc='center left', bbox_to_anchor=(.048, .855), frameon=False,
               ncol=2, handletextpad=.15, columnspacing=1.3, fontsize=10)

    labels, positions, y = [], [], 0
    for group in ('pq', 'rs', 'tu'):
        all_group = [r for r in candidates if r['case'] in group]
        shown = [r for r in scored if r['case'] in group]
        center = y + (max(1, len(shown)) - 1) / 2
        ax.text(-.26, center, f'{group[0].upper()}/{group[1].upper()}\n{len(shown)}/{len(all_group)} delivered',
                transform=ax.get_yaxis_transform(), va='center', color=muted, fontsize=10)
        if not shown:
            ax.text(292, y, 'No files delivered', va='center', color=muted, fontsize=10, style='italic')
            y += 1
        for row in shown:
            accepted = float(row['first_accepted_s'])
            returned = float(row['file_writing_exec_return_s'])
            ax.hlines(y, accepted, returned, color=accent, lw=1.7)
            ax.scatter([accepted, returned], [y, y], facecolors=['white', accent],
                       edgecolors=accent, s=42, linewidth=1.5, zorder=3)
            ax.text(returned + 1.6, y, f'{returned:.2f}', color=ink, va='center', fontsize=9)
            positions.append(y)
            labels.append(row['case'].upper() + row['repeat'])
            y += 1
        if group != 'tu':
            ax.axhline(y - .28, color='#dde5e7', lw=.8)
            y += .4

    ax.axvline(395, color='#a74d25', ls=(0, (3, 3)), lw=1.3)
    ax.text(395, 1.035, '395 s cutoff', transform=ax.get_xaxis_transform(), ha='right',
            color='#914321', fontsize=10, weight='bold')
    ax.set(xlim=(290, 397), ylim=(y - .35, -.7), xticks=[300, 320, 340, 360, 380, 395],
           xlabel='Seconds from session start', yticks=positions, yticklabels=labels)
    ax.xaxis.grid(True, color='#e8edee', lw=.65)
    ax.set_axisbelow(True)
    ax.spines[['left', 'right', 'top']].set_visible(False)
    ax.spines['bottom'].set_color('#b6c4c9')
    ax.tick_params(length=0, pad=5, labelcolor=muted)
    missing = sum(int(r['output_files']) == 0 for r in rows)
    fig.text(.055, .043, f'At 395 s, {len(scored)}/{len(candidates)} candidate runs and '
             f'0/{len(baseline)} baseline runs earned full credit.  {missing}/{len(rows)} had no output directory.',
             fontsize=10, color=ink)
    fig.savefig(FOLDER / 'delivery-timing.png', dpi=180, facecolor='white')
    plt.close(fig)


if __name__ == '__main__':
    main()
