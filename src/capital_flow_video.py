"""Render a selected trading day's saved capital-flow snapshots as an MP4."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def _trading_time_frame(day_replay: pd.DataFrame, sectors: list[str]) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    required = {"时间", "行业", "净流入额"}
    missing = required.difference(day_replay.columns)
    if missing:
        raise ValueError(f"回放数据缺少字段：{'、'.join(sorted(missing))}")
    if not sectors:
        raise ValueError("请至少选择一个板块后再生成视频。")

    frame = day_replay.loc[:, ["时间", "行业", "净流入额"]].copy()
    frame["时间戳"] = pd.to_datetime(frame["时间"], errors="coerce")
    frame["行业"] = frame["行业"].fillna("").astype(str).str.strip()
    frame["净流入额"] = pd.to_numeric(frame["净流入额"], errors="coerce")
    frame = frame.dropna(subset=["时间戳", "净流入额"])
    minutes = frame["时间戳"].dt.hour * 60 + frame["时间戳"].dt.minute
    in_session = (
        frame["时间戳"].dt.weekday.lt(5)
        & (minutes.between(9 * 60 + 30, 11 * 60 + 30) | minutes.between(13 * 60, 15 * 60))
    )
    frame = frame.loc[in_session].copy()
    if frame.empty:
        raise ValueError("所选交易日没有有效的 A 股交易时段快照。")
    frame = frame.loc[frame["行业"].isin(sectors)].copy()
    if frame.empty:
        raise ValueError("所选板块在该交易日没有有效的资金快照。")
    frame = frame.sort_values("时间戳").drop_duplicates(["时间戳", "行业"], keep="last")
    times = sorted(pd.Timestamp(value) for value in frame["时间戳"].drop_duplicates())
    if len(times) < 2:
        raise ValueError("所选板块至少需要两个交易时点，才能生成全天走势视频。")
    if not frame["净流入额"].notna().any():
        raise ValueError("所选板块没有有效的净流入数值。")
    return frame, times


def _render_snapshot_frame(
    frame: pd.DataFrame,
    time_points: list[pd.Timestamp],
    sectors: list[str],
    point_index: int,
    plt: Any,
):
    current_time = time_points[point_index]
    values = frame.loc[frame["时间戳"].eq(current_time), ["行业", "净流入额"]].drop_duplicates("行业", keep="last")
    values = values.sort_values("净流入额", ascending=True).copy()
    values["净流入亿元"] = values["净流入额"] / 1e8

    fig = plt.figure(figsize=(12.8, 7.2), dpi=100, facecolor="#080d16")
    fig.text(0.075, 0.955, "市场资金偏好分布", color="#f8fafc", fontsize=18, fontweight="bold", va="top")
    fig.text(0.93, 0.955, current_time.strftime("%Y-%m-%d  %H:%M"), color="#94a3b8", fontsize=11, ha="right", va="top")
    fig.text(0.075, 0.495, "当日板块资金流向走势", color="#f8fafc", fontsize=15, fontweight="bold", va="top")

    bar_ax = fig.add_axes([0.15, 0.545, 0.72, 0.34], facecolor="#080d16")
    bar_ax.axvline(0, color="#64748b", linewidth=0.9, zorder=1)
    if not values.empty:
        y_pos = list(range(len(values)))
        bar_colors = ["#ef4444" if value >= 0 else "#22c55e" for value in values["净流入亿元"]]
        bars = bar_ax.barh(y_pos, values["净流入亿元"], color=bar_colors, height=0.68, zorder=2)
        bar_ax.set_yticks(y_pos, labels=values["行业"].astype(str).tolist())
        max_value = max(1.0, float(values["净流入亿元"].abs().max()))
        bar_ax.set_xlim(-max_value * 1.23, max_value * 1.23)
        for bar, value in zip(bars, values["净流入亿元"]):
            offset = max_value * 0.018
            bar_ax.text(
                value + (offset if value >= 0 else -offset),
                bar.get_y() + bar.get_height() / 2,
                f"{value:+.2f}",
                color="#e2e8f0",
                fontsize=7.5,
                ha="left" if value >= 0 else "right",
                va="center",
                clip_on=False,
            )
    else:
        bar_ax.text(0.5, 0.5, "当前时点无选中板块数据", transform=bar_ax.transAxes,
                    color="#94a3b8", ha="center", va="center", fontsize=10)
        bar_ax.set_yticks([])
        bar_ax.set_xlim(-1, 1)
    bar_ax.tick_params(axis="x", colors="#94a3b8", labelsize=7, length=0)
    bar_ax.tick_params(axis="y", colors="#e2e8f0", labelsize=7, length=0, pad=4)
    bar_ax.grid(axis="x", color="#1e293b", linewidth=0.65)
    for spine in bar_ax.spines.values():
        spine.set_visible(False)
    bar_ax.set_xlabel("资金净额（亿元）", color="#cbd5e1", fontsize=8, labelpad=5)

    line_ax = fig.add_axes([0.105, 0.11, 0.76, 0.32], facecolor="#080d16")
    line_ax.axhline(0, color="#64748b", linewidth=0.8, zorder=1)
    pivot = frame.pivot_table(index="时间戳", columns="行业", values="净流入额", aggfunc="last")
    pivot = pivot.reindex(index=time_points, columns=sectors) / 1e8
    positions = list(range(point_index + 1))
    palette = [
        "#38bdf8", "#f472b6", "#facc15", "#a78bfa", "#34d399", "#fb923c",
        "#60a5fa", "#f87171", "#2dd4bf", "#c084fc", "#4ade80", "#fbbf24",
        "#22d3ee", "#e879f9", "#a3e635", "#fb7185", "#818cf8", "#fda4af",
    ]
    plotted = 0
    for sector_index, sector in enumerate(sectors):
        if sector not in pivot.columns:
            continue
        y_values = pivot[sector].iloc[:point_index + 1]
        if y_values.notna().any():
            line_ax.plot(positions, y_values.to_numpy(dtype=float), color=palette[sector_index % len(palette)],
                         linewidth=1.8, marker="o", markersize=2.2, label=sector, zorder=3)
            plotted += 1
    visible_values = pivot.iloc[:point_index + 1].to_numpy(dtype=float)
    finite_values = visible_values[pd.notna(visible_values)]
    extent = max(1.0, float(abs(finite_values).max()) if finite_values.size else 1.0)
    line_ax.set_ylim(-extent * 1.18, extent * 1.18)
    line_ax.set_xlim(0, max(1, len(time_points) - 1))
    tick_step = max(1, (len(time_points) + 5) // 6)
    tick_positions = list(range(0, len(time_points), tick_step))
    if tick_positions[-1] != len(time_points) - 1:
        tick_positions.append(len(time_points) - 1)
    line_ax.set_xticks(tick_positions, [time_points[index].strftime("%H:%M") for index in tick_positions])
    line_ax.tick_params(axis="both", colors="#94a3b8", labelsize=7, length=0, pad=4)
    line_ax.grid(color="#1e293b", linewidth=0.65)
    for spine in line_ax.spines.values():
        spine.set_color("#243244")
    line_ax.set_ylabel("净流入（亿元）", color="#cbd5e1", fontsize=8, labelpad=6)
    line_ax.set_xlabel("采集时间（午休时段已压缩）", color="#cbd5e1", fontsize=8, labelpad=5)
    if plotted:
        line_ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False,
                       labelcolor="#cbd5e1", fontsize=6.6, ncol=1, handlelength=1.6,
                       borderaxespad=0.0, labelspacing=0.33)
    else:
        line_ax.text(0.5, 0.5, "所选板块尚无有效曲线", transform=line_ax.transAxes,
                     color="#94a3b8", ha="center", va="center", fontsize=10)
    fig.text(0.93, 0.045, f"采集时点 {point_index + 1} / {len(time_points)}", color="#64748b",
             fontsize=8, ha="right")
    return fig


def render_capital_flow_video(
    day_replay: pd.DataFrame,
    sectors: list[str],
    output_path: str | Path,
    fps: int = 12,
    duration_seconds: int = 20,
) -> dict[str, Any]:
    """Render actual intraday snapshots into a progressive two-panel MP4."""
    try:
        import imageio
        import matplotlib
        import numpy as np
        matplotlib.use("Agg")
        from matplotlib import font_manager
        import matplotlib.pyplot as plt
        import imageio_ffmpeg  # noqa: F401  (ensures the bundled FFmpeg dependency exists)
    except ImportError as exc:
        raise RuntimeError("生成 MP4 需要安装 requirements.txt 中的 matplotlib、imageio 和 imageio-ffmpeg。") from exc

    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    for font_name in ("Microsoft YaHei", "Microsoft YaHei UI", "SimHei", "SimSun", "DengXian"):
        if font_name in available_fonts:
            plt.rcParams["font.sans-serif"] = [font_name, "DejaVu Sans"]
            break
    plt.rcParams["axes.unicode_minus"] = False

    frame, time_points = _trading_time_frame(day_replay, sectors)
    if fps < 1 or duration_seconds < 1:
        raise ValueError("视频帧率和时长必须是正整数。")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    total_frames = max(len(time_points), int(fps * duration_seconds))
    base_repeats, remainder = divmod(total_frames, len(time_points))
    latest_time = time_points[-1]
    latest_sectors = set(frame.loc[frame["时间戳"].eq(latest_time), "行业"].astype(str))
    missing_sectors = [sector for sector in sectors if sector not in latest_sectors]
    writer = None
    render_error = None
    completed = False
    try:
        writer = imageio.get_writer(
            str(output), format="FFMPEG", mode="I", fps=fps, codec="libx264",
            pixelformat="yuv420p", macro_block_size=1, ffmpeg_params=["-crf", "20"],
        )
        for point_index in range(len(time_points)):
            fig = _render_snapshot_frame(frame, time_points, sectors, point_index, plt)
            try:
                fig.canvas.draw()
                pixels = np.asarray(fig.canvas.buffer_rgba(), dtype=np.uint8)[..., :3].copy()
            finally:
                plt.close(fig)
            repeat_count = base_repeats + (1 if point_index < remainder else 0)
            for _ in range(repeat_count):
                writer.append_data(pixels)
        writer.close()
        writer = None
        completed = True
    except Exception as exc:
        render_error = exc
    finally:
        if writer is not None:
            try:
                writer.close()
            except Exception as close_error:
                if render_error is None:
                    render_error = close_error
        if not completed:
            try:
                output.unlink(missing_ok=True)
            except OSError:
                pass

    if render_error is not None:
        if isinstance(render_error, (ValueError, RuntimeError)):
            raise render_error
        raise RuntimeError(f"MP4 渲染或编码失败：{str(render_error)[:240]}") from render_error

    return {
        "output_path": str(output),
        "snapshot_count": len(time_points),
        "first_time": time_points[0].strftime("%H:%M"),
        "last_time": time_points[-1].strftime("%H:%M"),
        "missing_sectors": missing_sectors,
        "duration_seconds": total_frames / fps,
    }
