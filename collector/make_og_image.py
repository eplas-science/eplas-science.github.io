"""Draw collector/og-image.png, the preview shown when the site's link is shared (1200x630)."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

out = Path(__file__).parent / "og-image.png"
fig = plt.figure(figsize=(12, 6.3), dpi=100)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 12)
ax.set_ylim(0, 6.3)
ax.axis("off")
fig.patch.set_facecolor("#0f3b3a")

# Gently curving layers, like a resistivity section or soil horizons.
x = np.linspace(0, 12, 400)
for i, base in enumerate(np.linspace(0.35, 2.55, 9)):
    y = base + 0.16 * np.sin(x * 0.55 + i * 0.7) + 0.07 * np.sin(x * 1.7 + i)
    ax.plot(x, y, color="#5fb7a6", alpha=0.16 + 0.035 * i, linewidth=1.6)
# A root-like line reaching down through the layers.
t = np.linspace(0, 1, 120)
ax.plot(9.6 + 0.25 * np.sin(t * 9), 3.05 - 2.6 * t, color="#e9c46a", alpha=0.55, linewidth=2.2)

ax.text(0.85, 4.55, "EPLAS", color="white", fontsize=64, fontweight="bold", va="center", family="DejaVu Sans")
ax.text(0.9, 3.65, "Earth & planetary science, from plate tectonics to Mars", color="#cfe9e3", fontsize=24, va="center")
ax.text(0.9, 3.08, "News, research papers and jobs, updated twice a day", color="#9fd3c7", fontsize=19, va="center")
ax.text(11.15, 0.32, "eplas-science.github.io", color="#9fd3c7", fontsize=15, ha="right", va="center")
fig.savefig(out, dpi=100, facecolor=fig.get_facecolor())
print(out, "saved")
