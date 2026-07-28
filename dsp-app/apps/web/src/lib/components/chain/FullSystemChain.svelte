<script lang="ts">
  import {
    Background,
    BackgroundVariant,
    Controls,
    MarkerType,
    Position,
    SvelteFlow,
    type Edge,
    type Node,
  } from '@xyflow/svelte';
  import '@xyflow/svelte/dist/style.css';

  import { dspState } from '$lib/stores/dsp';
  import type { AppAudioStream, HardwareStage, PipeWireSink } from '@aural/shared';

  type ChainNodeData = {
    label: string;
  };

  type ChainNode = Node<ChainNodeData>;
  type ChainEdge = Edge;

  const DSP_SINK_ORDER = [
    'effect_input.headphone_dsp',
    'effect_input.headphone_dsp_crossfeed',
    'effect_input.headphone_dsp_room',
    'effect_input.headphone_dsp_movie',
  ];

  let nodes: ChainNode[] = $state.raw([]);
  let edges: ChainEdge[] = $state.raw([]);

  function formatRate(rate: number | null | undefined): string {
    if (!rate) return 'idle';
    return rate >= 1000 ? `${rate / 1000}k` : `${rate}Hz`;
  }

  function formatChannels(channels: number | null | undefined): string {
    if (!channels) return '';
    if (channels === 2) return 'stereo';
    if (channels === 6) return '5.1';
    if (channels === 8) return '7.1';
    return `${channels}ch`;
  }

  function sinkShortName(sink: PipeWireSink): string {
    if (sink.name.endsWith('_movie')) return 'Movie';
    if (sink.description === 'Headphone DSP') return 'Clean';
    return sink.description.replace('Headphone DSP + ', '').replace('Topping ', '');
  }

  function appFormat(stream: AppAudioStream): string {
    const parts = [formatChannels(stream.channels), formatRate(stream.sampleRate), stream.format].filter(Boolean);
    return parts.join(' / ');
  }

  function hardwareDetail(stage: HardwareStage): string {
    if (stage.format) {
      return `${formatRate(stage.format.sampleRate)} / ${stage.format.bitDepth}bit / ${stage.format.format}`;
    }
    return stage.description;
  }

  function safeId(value: string | number): string {
    return String(value).replace(/[^a-zA-Z0-9_-]/g, '_');
  }

  function nodeStyle(kind: 'app' | 'sink' | 'hardware', active = false): string {
    const palette = {
      app: {
        border: 'rgba(245, 158, 11, 0.45)',
        background: 'rgba(245, 158, 11, 0.10)',
      },
      sink: {
        border: 'rgba(163, 120, 255, 0.48)',
        background: 'rgba(163, 120, 255, 0.12)',
      },
      hardware: {
        border: 'rgba(52, 211, 153, 0.42)',
        background: 'rgba(52, 211, 153, 0.10)',
      },
    }[kind];

    return [
      'width: 210px',
      'min-height: 76px',
      'border-radius: 10px',
      `border: 1px solid ${palette.border}`,
      `background: linear-gradient(135deg, ${palette.background}, rgba(18, 18, 20, 0.94))`,
      'color: var(--color-text-primary)',
      'box-shadow: 0 14px 36px rgba(0, 0, 0, 0.26)',
      'font-family: inherit',
      'font-size: 11px',
      'line-height: 1.35',
      'white-space: pre-line',
      active ? 'filter: drop-shadow(0 0 12px rgba(245, 158, 11, 0.32))' : '',
    ].filter(Boolean).join('; ');
  }

  function nodeLabel(title: string, eyebrow: string, details: string[]): string {
    return [eyebrow.toUpperCase(), title, ...details].filter(Boolean).join('\n');
  }

  function buildNodes(streams: AppAudioStream[], sinks: PipeWireSink[], hardware: HardwareStage[]): ChainNode[] {
    const appNodes: ChainNode[] = streams.length > 0
      ? streams.map((stream, index) => ({
          id: `app-${safeId(stream.id)}`,
          type: 'input',
          data: {
            label: nodeLabel(stream.applicationName, stream.state, [
              appFormat(stream),
              stream.sinkDescription ?? stream.sinkName ?? 'unrouted',
            ]),
          },
          position: { x: 0, y: index * 118 },
          sourcePosition: Position.Right,
          style: nodeStyle('app', stream.state === 'active'),
        }))
      : [{
          id: 'app-idle',
          type: 'input',
          data: { label: nodeLabel('No app streams', 'idle', ['PipeWire has no connected sink inputs']) },
          position: { x: 0, y: 120 },
          sourcePosition: Position.Right,
          style: nodeStyle('app'),
        }];

    const sinkNodes = sinks.map((sink, index) => ({
      id: `sink-${safeId(sink.name)}`,
      type: 'default',
      data: {
        label: nodeLabel(sinkShortName(sink), sink.role, [
          `${formatChannels(sink.channels)} ${formatRate(sink.sampleRate)}`.trim(),
          `${sink.activeStreams} active stream${sink.activeStreams === 1 ? '' : 's'}`,
          sink.isDefault ? 'default music route' : '',
        ]),
      },
      position: { x: 320, y: index * 106 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      style: nodeStyle('sink', sink.activeStreams > 0 || sink.isDefault),
    }));

    const hardwareNodes = hardware.map((stage, index) => ({
      id: `hardware-${safeId(stage.id)}`,
      type: index === hardware.length - 1 ? 'output' : 'default',
      data: {
        label: nodeLabel(stage.name, stage.role, [
          hardwareDetail(stage),
          stage.role === 'amp' ? 'analog gain stage' : '',
        ]),
      },
      position: { x: 690 + index * 250, y: 130 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      style: nodeStyle('hardware', index === 0),
    }));

    return [...appNodes, ...sinkNodes, ...hardwareNodes];
  }

  function buildEdges(streams: AppAudioStream[], sinks: PipeWireSink[], hardware: HardwareStage[]): ChainEdge[] {
    const knownSinkNames = new Set(sinks.map((sink) => sink.name));
    const routeEdges = streams
      .filter((stream) => stream.sinkName && knownSinkNames.has(stream.sinkName))
      .map((stream) => ({
        id: `edge-${safeId(stream.id)}-${safeId(stream.sinkName ?? '')}`,
        source: `app-${safeId(stream.id)}`,
        target: `sink-${safeId(stream.sinkName ?? '')}`,
        animated: stream.state === 'active',
        markerEnd: { type: MarkerType.ArrowClosed, color: '#f59e0b' },
        style: `stroke: ${stream.state === 'active' ? '#f59e0b' : 'rgba(245, 158, 11, 0.48)'}; stroke-width: ${stream.state === 'active' ? 2.2 : 1.4}`,
      }));

    const firstHardware = hardware[0];
    const sinkEdges = firstHardware
      ? sinks.map((sink) => ({
          id: `edge-${safeId(sink.name)}-${safeId(firstHardware.id)}`,
          source: `sink-${safeId(sink.name)}`,
          target: `hardware-${safeId(firstHardware.id)}`,
          animated: sink.activeStreams > 0,
          markerEnd: { type: MarkerType.ArrowClosed, color: '#34d399' },
          style: `stroke: ${sink.activeStreams > 0 ? '#34d399' : 'rgba(52, 211, 153, 0.34)'}; stroke-width: ${sink.activeStreams > 0 ? 2.1 : 1.2}`,
        }))
      : [];

    const hardwareEdges = hardware.slice(0, -1).map((stage, index) => {
      const next = hardware[index + 1];
      return {
        id: `edge-${safeId(stage.id)}-${safeId(next.id)}`,
        source: `hardware-${safeId(stage.id)}`,
        target: `hardware-${safeId(next.id)}`,
        markerEnd: { type: MarkerType.ArrowClosed, color: '#34d399' },
        style: 'stroke: rgba(52, 211, 153, 0.66); stroke-width: 1.7',
      };
    });

    return [...routeEdges, ...sinkEdges, ...hardwareEdges];
  }

  let appStreams = $derived.by(() => {
    const streams = $dspState?.system.streams ?? [];
    return [...streams].sort((a, b) => Number(a.state === 'paused') - Number(b.state === 'paused'));
  });

  let dspSinks = $derived.by(() => {
    const sinks = $dspState?.system.sinks ?? [];
    return sinks
      .filter((sink) => sink.role === 'music' || sink.role === 'movie')
      .sort((a, b) => DSP_SINK_ORDER.indexOf(a.name) - DSP_SINK_ORDER.indexOf(b.name));
  });

  let hardware = $derived($dspState?.system.hardware ?? []);

  let defaultSinkLabel = $derived.by(() => {
    const defaultSink = dspSinks.find((sink) => sink.isDefault);
    return defaultSink ? sinkShortName(defaultSink).toLowerCase() : 'clean';
  });

  $effect(() => {
    nodes = buildNodes(appStreams, dspSinks, hardware);
    edges = buildEdges(appStreams, dspSinks, hardware);
  });
</script>

<section class="glass-subtle rounded-xl p-4">
  <div class="flex items-center justify-between gap-3 mb-3">
    <div>
      <div class="text-[10px] text-text-tertiary uppercase tracking-wider">Full Playback Graph</div>
      <div class="text-xs text-text-secondary mt-0.5">Live app streams, PipeWire virtual sinks, DSP routing, and hardware output.</div>
    </div>
    {#if $dspState?.system.defaultSinkName}
      <div class="text-[10px] font-mono text-text-tertiary shrink-0">
        default <span class="text-amber-dim">{defaultSinkLabel}</span>
      </div>
    {/if}
  </div>

  <div class="chain-flow h-[430px] overflow-hidden rounded-lg border border-border/60 bg-surface-0/35">
    <SvelteFlow
      {nodes}
      {edges}
      fitView
      minZoom={0.45}
      maxZoom={1.35}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable={false}
      proOptions={{ hideAttribution: true }}
    >
      <Background variant={BackgroundVariant.Dots} gap={18} size={1} />
      <Controls showLock={false} />
    </SvelteFlow>
  </div>
</section>

<style>
  .chain-flow :global(.svelte-flow) {
    background: radial-gradient(circle at 18% 20%, rgba(245, 158, 11, 0.08), transparent 28%),
      linear-gradient(135deg, rgba(20, 20, 24, 0.88), rgba(10, 10, 12, 0.96));
  }

  .chain-flow :global(.svelte-flow__node) {
    border-color: transparent;
    padding: 10px 12px;
    text-align: left;
  }

  .chain-flow :global(.svelte-flow__node strong),
  .chain-flow :global(.svelte-flow__node-default),
  .chain-flow :global(.svelte-flow__node-input),
  .chain-flow :global(.svelte-flow__node-output) {
    color: var(--color-text-primary);
  }

  .chain-flow :global(.svelte-flow__handle) {
    width: 7px;
    height: 7px;
    border: 1px solid rgba(245, 158, 11, 0.72);
    background: rgba(18, 18, 20, 0.96);
  }

  .chain-flow :global(.svelte-flow__edge-path) {
    filter: drop-shadow(0 0 5px rgba(245, 158, 11, 0.12));
  }

  .chain-flow :global(.svelte-flow__controls) {
    overflow: hidden;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    background: rgba(18, 18, 20, 0.82);
  }

  .chain-flow :global(.svelte-flow__controls-button) {
    border-color: rgba(255, 255, 255, 0.08);
    background: rgba(18, 18, 20, 0.82);
    color: var(--color-text-secondary);
    fill: var(--color-text-secondary);
  }
</style>
