#!/usr/bin/env node

import { execFileSync, spawnSync } from 'node:child_process';
import {
  accessSync,
  constants,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SCRIPT_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(SCRIPT_DIRECTORY, '..');
const VIDEO_WIDTH = 1280;
const VIDEO_HEIGHT = 800;
const FRAME_RATE = 60;

const PRESETS = {
  native: {
    popupWidth: 430,
    popupHeight: 260,
    cursorSize: 24,
    intro: 0,
    duration: 11.833333,
    audioDuration: 11.83,
    outputGain: 1,
  },
  tweet: {
    popupWidth: 760,
    popupHeight: 460,
    cursorSize: 42,
    intro: 0.9,
    duration: 12.733333,
    audioDuration: 12.73,
    outputGain: 0.9,
  },
};

const REQUIRED_STATES = [
  '00-ready.png',
  '01-billy.png',
  '03-tibo.png',
  '05-andrew.png',
  '06-confirmed.png',
  'cursor-05.png',
];

const HELP = `Model Finder video renderer

Usage:
  node scripts/render-video.mjs --runtime PATH --output PATH [options]

Required:
  --runtime PATH         Prepared runtime JSON produced by model_finder.py
  --output PATH          Destination .mp4 file (overwritten if it exists)

Options:
  --preset NAME          tweet (default) or native
  --background PATH      Screenshot or image placed behind the popup
                         (default: a neutral 1280x800 canvas)
  --states DIRECTORY     Use an existing set of rendered popup states
  --popup-binary PATH    Native renderer used when --states is omitted
                         (default: .build/model-finder-popup)
  --ffmpeg COMMAND       ffmpeg executable (default: MODEL_FINDER_FFMPEG,
                         FFMPEG, then ffmpeg from PATH)
  --magick COMMAND       ImageMagick executable (default: MODEL_FINDER_MAGICK,
                         MAGICK, then magick from PATH)
  --no-preview           Do not create the sibling *-preview.png file
  --help                 Show this help

The tweet preset starts with a readable 0.65-second cover, dissolves it, and
replays the native 0.34-second entrance at a feed-friendly size. The native
preset preserves the popup's relative desktop size and starts with the native
entrance. Both are 1280x800, 60 fps H.264/AAC videos.
`;

class CliError extends Error {}

function parseArguments(argv) {
  const options = {
    preset: 'tweet',
    preview: true,
    ffmpeg: process.env.MODEL_FINDER_FFMPEG || process.env.FFMPEG || 'ffmpeg',
    magick: process.env.MODEL_FINDER_MAGICK || process.env.MAGICK || 'magick',
  };
  const valueFlags = new Map([
    ['--runtime', 'runtime'],
    ['--output', 'output'],
    ['--preset', 'preset'],
    ['--background', 'background'],
    ['--states', 'states'],
    ['--popup-binary', 'popupBinary'],
    ['--ffmpeg', 'ffmpeg'],
    ['--magick', 'magick'],
  ]);

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === '--help' || argument === '-h') {
      options.help = true;
      continue;
    }
    if (argument === '--no-preview') {
      options.preview = false;
      continue;
    }
    const key = valueFlags.get(argument);
    if (!key) throw new CliError(`unknown option: ${argument}`);
    const value = argv[index + 1];
    if (!value || value.startsWith('--')) throw new CliError(`${argument} requires a value`);
    options[key] = value;
    index += 1;
  }

  return options;
}

function expandPath(value) {
  if (value === '~') return os.homedir();
  if (value.startsWith('~/')) return path.join(os.homedir(), value.slice(2));
  return path.resolve(value);
}

function requireFile(value, label) {
  const resolved = expandPath(value);
  if (!existsSync(resolved) || !statSync(resolved).isFile()) {
    throw new CliError(`${label} is not a file: ${resolved}`);
  }
  return resolved;
}

function requireDirectory(value, label) {
  const resolved = expandPath(value);
  if (!existsSync(resolved) || !statSync(resolved).isDirectory()) {
    throw new CliError(`${label} is not a directory: ${resolved}`);
  }
  return resolved;
}

function resolveRuntimeFile(value, runtimeDirectory, label, optional = false) {
  if (value === undefined || value === null || value === '') {
    if (optional) return null;
    throw new CliError(`${label} is required in the runtime JSON`);
  }
  if (typeof value !== 'string') throw new CliError(`${label} must be a path string`);
  const candidate = value.startsWith('~/')
    ? expandPath(value)
    : path.resolve(runtimeDirectory, value);
  if (!existsSync(candidate) || !statSync(candidate).isFile()) {
    throw new CliError(`${label} is not a file: ${candidate}`);
  }
  return candidate;
}

function readRuntime(runtimePath) {
  let runtime;
  try {
    runtime = JSON.parse(readFileSync(runtimePath, 'utf8'));
  } catch (error) {
    if (error instanceof SyntaxError) throw new CliError(`runtime JSON is invalid: ${error.message}`);
    throw error;
  }
  if (!runtime || typeof runtime !== 'object' || Array.isArray(runtime)) {
    throw new CliError('runtime JSON must contain an object');
  }
  if (!runtime.target || typeof runtime.target.displayName !== 'string' || !runtime.target.displayName.trim()) {
    throw new CliError('runtime target.displayName must be a non-empty string');
  }
  if (!Array.isArray(runtime.members) || runtime.members.length !== 5) {
    throw new CliError('runtime members must contain exactly five entries');
  }
  if (!runtime.popup || typeof runtime.popup !== 'object') {
    throw new CliError('runtime popup must be an object');
  }
  if (!runtime.popup.theme || typeof runtime.popup.theme !== 'object') {
    throw new CliError('runtime popup.theme must be an object');
  }
  return runtime;
}

function requireTool(command, label) {
  const candidate = command.includes('/') || command.startsWith('~') ? expandPath(command) : command;
  if (candidate.includes('/')) {
    try {
      accessSync(candidate, constants.X_OK);
    } catch {
      throw new CliError(`${label} is not executable: ${candidate}`);
    }
  }
  const result = spawnSync(candidate, ['-version'], { stdio: 'ignore' });
  if (result.error || result.status !== 0) {
    throw new CliError(`${label} was not found or could not run: ${candidate}`);
  }
  return candidate;
}

function run(command, arguments_, label) {
  try {
    execFileSync(command, arguments_, { stdio: 'inherit' });
  } catch (error) {
    throw new CliError(`${label} failed${error.status === undefined ? '' : ` (exit ${error.status})`}`);
  }
}

// CAMediaTimingFunction.easeOut is cubic-bezier(0, 0, 0.58, 1). Invert its
// x coordinate so the generated scale and alpha match the native 0.34s reveal.
function nativeEaseOut(progress) {
  if (progress <= 0) return 0;
  if (progress >= 1) return 1;
  let low = 0;
  let high = 1;
  for (let iteration = 0; iteration < 40; iteration += 1) {
    const parameter = (low + high) / 2;
    const x = 3 * (1 - parameter) * parameter * parameter * 0.58 + parameter ** 3;
    if (x < progress) low = parameter;
    else high = parameter;
  }
  const parameter = (low + high) / 2;
  return 3 * (1 - parameter) * parameter * parameter + parameter ** 3;
}

function renderVideo(options) {
  if (!options.runtime) throw new CliError('--runtime is required');
  if (!options.output) throw new CliError('--output is required');
  if (!Object.hasOwn(PRESETS, options.preset)) {
    throw new CliError(`--preset must be one of: ${Object.keys(PRESETS).join(', ')}`);
  }

  const runtimePath = requireFile(options.runtime, '--runtime');
  const outputPath = expandPath(options.output);
  if (path.extname(outputPath).toLowerCase() !== '.mp4') {
    throw new CliError('--output must end in .mp4');
  }
  const outputDirectory = path.dirname(outputPath);
  mkdirSync(outputDirectory, { recursive: true });
  const backgroundPath = options.background
    ? requireFile(options.background, '--background')
    : null;
  const ffmpeg = requireTool(options.ffmpeg, 'ffmpeg');
  const magick = requireTool(options.magick, 'ImageMagick');
  const runtime = readRuntime(runtimePath);
  const runtimeDirectory = path.dirname(runtimePath);
  const cursorPath = resolveRuntimeFile(runtime.popup.theme.cursor, runtimeDirectory, 'popup.theme.cursor');
  const cursorActivePath = resolveRuntimeFile(
    runtime.popup.theme.cursorActive,
    runtimeDirectory,
    'popup.theme.cursorActive',
  );
  const sounds = {
    ready: resolveRuntimeFile(runtime.popup.sounds?.ready, runtimeDirectory, 'popup.sounds.ready', true),
    enter: resolveRuntimeFile(runtime.popup.sounds?.enter, runtimeDirectory, 'popup.sounds.enter', true),
    confirm: resolveRuntimeFile(runtime.popup.sounds?.confirm, runtimeDirectory, 'popup.sounds.confirm', true),
  };
  const preset = PRESETS[options.preset];
  const temporaryRoot = mkdtempSync(path.join(os.tmpdir(), 'model-finder-video-'));

  try {
    const frameDirectory = path.join(temporaryRoot, 'frames');
    mkdirSync(frameDirectory, { recursive: true });
    let statesDirectory;
    if (options.states) {
      statesDirectory = requireDirectory(options.states, '--states');
    } else {
      statesDirectory = path.join(temporaryRoot, 'states');
      mkdirSync(statesDirectory, { recursive: true });
      const binary = requireFile(
        options.popupBinary || path.join(PROJECT_ROOT, '.build', 'model-finder-popup'),
        '--popup-binary',
      );
      try {
        accessSync(binary, constants.X_OK);
      } catch {
        throw new CliError(`--popup-binary is not executable: ${binary}`);
      }
      run(
        binary,
        [runtimePath, '--render-states', statesDirectory, '--no-cursor'],
        'popup state rendering',
      );
    }

    for (const name of REQUIRED_STATES) {
      requireFile(path.join(statesDirectory, name), `rendered state ${name}`);
    }

    const basePath = path.join(frameDirectory, 'base.png');
    if (backgroundPath) {
      run(magick, [
        backgroundPath,
        '-resize', `${VIDEO_WIDTH}x${VIDEO_HEIGHT}`,
        '-background', '#171717',
        '-gravity', 'center',
        '-extent', `${VIDEO_WIDTH}x${VIDEO_HEIGHT}`,
        basePath,
      ], 'background preparation');
    } else {
      run(magick, [
        '-size', `${VIDEO_WIDTH}x${VIDEO_HEIGHT}`,
        'xc:#171717',
        basePath,
      ], 'neutral background preparation');
    }

    const { popupWidth, popupHeight } = preset;
    const frame = (source, name, scale = 1, opacity = 1) => {
      const destination = path.join(frameDirectory, `${name}.png`);
      run(magick, [
        basePath,
        '(', path.join(statesDirectory, source),
        '-resize', `${Math.round(popupWidth * scale)}x${Math.round(popupHeight * scale)}!`,
        '-alpha', 'set',
        '-channel', 'A',
        '-evaluate', 'multiply', String(opacity),
        '+channel', ')',
        '-gravity', 'center',
        '-compose', 'over',
        '-composite',
        destination,
      ], `frame generation (${name})`);
      return path.basename(destination);
    };

    const concat = ['ffconcat version 1.0'];
    const append = (file, seconds) => {
      concat.push(`file '${file}'`, `option framerate ${FRAME_RATE}`, `duration ${seconds.toFixed(9)}`);
    };

    if (options.preset === 'tweet') {
      append(frame('00-ready.png', 'opening-cover'), 0.65);
      for (let number = 1; number <= 9; number += 1) {
        const opacity = nativeEaseOut(1 - number / 9);
        append(frame(
          '00-ready.png',
          `cover-out-${number}`,
          0.975 + 0.025 * opacity,
          opacity,
        ), 1 / FRAME_RATE);
      }
      append(path.basename(basePath), 0.1);
    }

    for (let number = 0; number < 21; number += 1) {
      const eased = nativeEaseOut(number / FRAME_RATE / 0.34);
      append(frame(
        '00-ready.png',
        `fade-${String(number).padStart(2, '0')}`,
        0.91 + 0.09 * eased,
        eased,
      ), 1 / FRAME_RATE);
    }
    append(frame('00-ready.png', 'ready'), 4.6 - 21 / FRAME_RATE);
    append(frame('cursor-05.png', 'hover'), 0.58);
    append(frame('01-billy.png', 'member-one'), 1.15);
    append(frame('03-tibo.png', 'members-two-three'), 1.85);
    append(frame('05-andrew.png', 'all-accepted'), 0.45);
    const confirmed = frame('06-confirmed.png', 'confirmed');
    append(confirmed, 3.2);
    concat.push(`file '${confirmed}'`, `option framerate ${FRAME_RATE}`);
    const timelinePath = path.join(frameDirectory, 'timeline.ffconcat');
    writeFileSync(timelinePath, `${concat.join('\n')}\n`);

    const intro = preset.intro;
    const left = (VIDEO_WIDTH - popupWidth) / 2;
    const top = (VIDEO_HEIGHT - popupHeight) / 2;
    const progress = `min(1,max(0,(t-${3.53 + intro})/1.45))`;
    const ease = `(pow(${progress},2)*(3-2*${progress}))`;
    const cursorX = `${left}+(547-352*${ease})*${popupWidth}/580`;
    const cursorY = `${top}+(326-34*pow(${ease},5))*${popupHeight}/351`;
    const delay = milliseconds => milliseconds + Math.round(intro * 1000);
    const filters = [
      `[0:v]fps=${FRAME_RATE},format=rgba[scene]`,
      `[1:v]scale=${preset.cursorSize}:${preset.cursorSize}:flags=neighbor,format=rgba[cursor]`,
      `[2:v]scale=${preset.cursorSize}:${preset.cursorSize}:flags=neighbor,format=rgba[active]`,
      `[scene][cursor]overlay=x='${cursorX}':y='${cursorY}':eval=frame:enable='gte(t,${3.53 + intro})*lt(t,${4.60 + intro})':shortest=1[normal]`,
      `[normal][active]overlay=x='${cursorX}':y='${cursorY}':eval=frame:enable='gte(t,${4.60 + intro})*lt(t,${5.18 + intro})':shortest=1,format=yuv420p,setsar=1[v]`,
    ];

    const ffmpegArguments = [
      '-y', '-hide_banner', '-loglevel', 'warning',
      '-f', 'concat', '-safe', '0', '-i', timelinePath,
      '-loop', '1', '-framerate', String(FRAME_RATE), '-i', cursorPath,
      '-loop', '1', '-framerate', String(FRAME_RATE), '-i', cursorActivePath,
    ];
    let inputIndex = 3;
    const audioLabels = [];
    if (sounds.ready) {
      ffmpegArguments.push('-i', sounds.ready);
      filters.push(`[${inputIndex}:a]adelay=${delay(340)}:all=1,volume=1.0[ready]`);
      audioLabels.push('[ready]');
      inputIndex += 1;
    }
    if (sounds.enter) {
      ffmpegArguments.push('-i', sounds.enter);
      filters.push(`[${inputIndex}:a]adelay=${delay(4980)}:all=1,volume=0.95[enter]`);
      audioLabels.push('[enter]');
      inputIndex += 1;
    }
    if (sounds.confirm) {
      ffmpegArguments.push('-i', sounds.confirm);
      filters.push(`[${inputIndex}:a]asplit=5[confirm0][confirm1][confirm2][confirm3][confirm4]`);
      for (const [number, milliseconds] of [5180, 6330, 6450, 8180, 8300].entries()) {
        filters.push(
          `[confirm${number}]adelay=${delay(milliseconds)}:all=1,volume=0.38[tag${number}]`,
        );
        audioLabels.push(`[tag${number}]`);
      }
      inputIndex += 1;
    }
    filters.push(`anullsrc=r=48000:cl=stereo:d=${preset.audioDuration}[silence]`);
    const mixInputs = ['[silence]', ...audioLabels];
    filters.push(
      `${mixInputs.join('')}amix=inputs=${mixInputs.length}:duration=longest:dropout_transition=0:normalize=0,` +
      `alimiter=limit=0.98,volume=${preset.outputGain},atrim=0:${preset.audioDuration},aresample=48000[a]`,
    );

    ffmpegArguments.push(
      '-filter_complex', filters.join(';'),
      '-map', '[v]', '-map', '[a]',
      '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-r', String(FRAME_RATE),
      '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
      '-movflags', '+faststart', '-t', String(preset.duration),
      outputPath,
    );
    run(ffmpeg, ffmpegArguments, 'video encoding');

    if (options.preview) {
      const extension = path.extname(outputPath);
      const stem = outputPath.slice(0, -extension.length);
      const previewPath = `${stem}-preview.png`;
      run(ffmpeg, [
        '-y', '-hide_banner', '-loglevel', 'error', '-ss', '0.4',
        '-i', outputPath, '-frames:v', '1', previewPath,
      ], 'preview generation');
      if (options.preset === 'tweet') {
        run(ffmpeg, [
          '-y', '-hide_banner', '-loglevel', 'error',
          '-i', outputPath, '-frames:v', '1', `${stem}-cover.png`,
        ], 'cover generation');
      }
    }
  } finally {
    rmSync(temporaryRoot, { recursive: true, force: true });
  }

  console.log(
    `Created ${outputPath}: ${preset.popupWidth}x${preset.popupHeight}px popup, ` +
    'native 0.34s reveal, smooth 60 fps cursor.',
  );
}

function main() {
  const options = parseArguments(process.argv.slice(2));
  if (options.help) {
    process.stdout.write(HELP);
    return;
  }
  renderVideo(options);
}

try {
  main();
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`render-video: ${message}`);
  process.exitCode = 1;
}
