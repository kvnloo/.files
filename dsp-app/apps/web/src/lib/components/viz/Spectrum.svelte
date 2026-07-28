<script lang="ts">
  import { onMount } from 'svelte';
  import { spectrumBars, connectSpectrum, disconnectSpectrum } from '$lib/stores/spectrum';
  import { spatialMode } from '$lib/stores/dsp';

  let canvas: HTMLCanvasElement;
  let container: HTMLDivElement;
  let ctx: CanvasRenderingContext2D;
  let animationId: number;
  let isVisible = true;
  let smoothedBars: number[] = new Array(48).fill(0);
  let prevBars: number[] = new Array(48).fill(0);

  // Mode-specific visual themes
  const modeThemes = {
    clean: {
      barColor: 'rgba(212, 163, 74, 0.9)',
      glowColor: 'rgba(212, 163, 74, 0.3)',
      bloomRadius: 8,
      barWidth: 0.7,
    },
    crossfeed: {
      barColor: 'rgba(212, 163, 74, 0.8)',
      glowColor: 'rgba(212, 163, 74, 0.25)',
      bloomRadius: 14,
      barWidth: 0.8,
    },
    room: {
      barColor: 'rgba(155, 114, 207, 0.7)',
      glowColor: 'rgba(155, 114, 207, 0.2)',
      bloomRadius: 20,
      barWidth: 0.9,
    },
  };

  function resizeCanvas() {
    if (!canvas) return;
    const rect = canvas.parentElement!.getBoundingClientRect();
    canvas.width = rect.width * devicePixelRatio;
    canvas.height = rect.height * devicePixelRatio;
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;
    ctx?.scale(devicePixelRatio, devicePixelRatio);
  }

  function draw() {
    if (!ctx || !canvas) return;

    const w = canvas.width / devicePixelRatio;
    const h = canvas.height / devicePixelRatio;
    const mode = $spatialMode;
    const theme = modeThemes[mode];
    const bars = $spectrumBars;
    const numBars = bars.length || 48;

    // Smooth bars with exponential decay
    for (let i = 0; i < numBars; i++) {
      const target = bars[i] ?? 0;
      smoothedBars[i] = smoothedBars[i] * 0.75 + target * 0.25;
      // Gravity fall
      if (smoothedBars[i] < prevBars[i]) {
        smoothedBars[i] = Math.max(smoothedBars[i], prevBars[i] - 0.02);
      }
      prevBars[i] = smoothedBars[i];
    }

    // Clear
    ctx.clearRect(0, 0, w, h);

    const gap = 2;
    const totalGap = gap * (numBars - 1);
    const barW = (w - totalGap) / numBars * theme.barWidth;
    const barOffset = (w - totalGap) / numBars * (1 - theme.barWidth) / 2;
    const maxH = h * 0.85;

    // Draw glow layer (behind bars)
    ctx.save();
    ctx.filter = `blur(${theme.bloomRadius}px)`;
    for (let i = 0; i < numBars; i++) {
      const barH = smoothedBars[i] * maxH;
      if (barH < 1) continue;
      const x = i * (w / numBars) + barOffset;
      const y = h - barH;
      ctx.fillStyle = theme.glowColor;
      ctx.fillRect(x, y, barW, barH);
    }
    ctx.restore();

    // Draw bars
    for (let i = 0; i < numBars; i++) {
      const barH = smoothedBars[i] * maxH;
      if (barH < 1) continue;
      const x = i * (w / numBars) + barOffset;
      const y = h - barH;

      // Gradient from bottom (dimmer) to top (brighter)
      const grad = ctx.createLinearGradient(x, h, x, y);
      grad.addColorStop(0, 'rgba(212, 163, 74, 0.3)');
      grad.addColorStop(1, theme.barColor);
      ctx.fillStyle = grad;

      // Rounded top
      const radius = Math.min(barW / 2, 3);
      ctx.beginPath();
      ctx.moveTo(x, h);
      ctx.lineTo(x, y + radius);
      ctx.quadraticCurveTo(x, y, x + radius, y);
      ctx.lineTo(x + barW - radius, y);
      ctx.quadraticCurveTo(x + barW, y, x + barW, y + radius);
      ctx.lineTo(x + barW, h);
      ctx.fill();
    }

    // Subtle reflection
    ctx.save();
    ctx.globalAlpha = 0.08;
    ctx.scale(1, -0.3);
    ctx.translate(0, -h / 0.3 - h);
    for (let i = 0; i < numBars; i++) {
      const barH = smoothedBars[i] * maxH;
      if (barH < 2) continue;
      const x = i * (w / numBars) + barOffset;
      const y = h - barH;
      ctx.fillStyle = theme.barColor;
      ctx.fillRect(x, y, barW, barH);
    }
    ctx.restore();

    animationId = requestAnimationFrame(draw);
  }

  onMount(() => {
    ctx = canvas.getContext('2d')!;
    resizeCanvas();
    connectSpectrum();
    animationId = requestAnimationFrame(draw);

    const resizeObserver = new ResizeObserver(resizeCanvas);
    resizeObserver.observe(canvas.parentElement!);

    const intersectionObserver = new IntersectionObserver(
      ([entry]) => {
        isVisible = entry.isIntersecting;
        if (isVisible) {
          connectSpectrum();
          animationId = requestAnimationFrame(draw);
        } else {
          cancelAnimationFrame(animationId);
          disconnectSpectrum();
        }
      },
      { threshold: 0 },
    );
    intersectionObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      intersectionObserver.disconnect();
      cancelAnimationFrame(animationId);
      disconnectSpectrum();
    };
  });
</script>

<div bind:this={container} class="relative w-full h-full overflow-hidden rounded-xl">
  <!-- Ambient gradient background -->
  <div class="absolute inset-0 bg-gradient-to-t from-surface-0/80 via-transparent to-transparent pointer-events-none"></div>
  <canvas bind:this={canvas} class="w-full h-full"></canvas>
  <!-- Bottom fade -->
  <div class="absolute bottom-0 left-0 right-0 h-8 bg-gradient-to-t from-void to-transparent pointer-events-none"></div>
</div>
