// Runs packages/widgets/Specs/VoxelInspector/__tests__/VoxelInspectorViewModelSpec.js through
// Cesium's own Karma/Jasmine harness (headless Chromium) and writes a JUnit report. Invoked by
// test.sh after `gulp build --workspace @cesium/engine` (needed because @cesium/widgets imports
// @cesium/engine, which must have its own generated index.js/exports before the widgets bundle
// can resolve them) and `gulp build --workspace @cesium/widgets` (which rebuilds the widgets
// spec bundle restricted to just this one spec file) have run.
//
// The spec this task scores drives VoxelInspectorViewModel directly with a lightweight mock
// scene/primitive -- it never opens a WebGL context (the class under test only ever calls
// `scene.requestRender()` on its scene argument) -- but it still needs a real browser DOM to run
// through Karma/Jasmine like every other spec in this repo (there is no lighter node-only runner
// wired up here). The file/proxy entries below mirror gulpfile.js's own `test --workspace`
// code path exactly (files/proxies are keyed off the engine package regardless of which
// workspace is under test, since engine is "the lowest level dependency" every other package's
// bundle resolves against).
import karma from "karma";
import path from "path";

const karmaConfigFile = path.resolve("./Specs/karma.conf.cjs");
const REPORT_DIR = "/logs/verifier";
const REPORT_FILE = "karma-junit.xml";

const files = [
  {
    pattern: "packages/widgets/Build/Specs/karma-main.js",
    included: true,
    type: "module",
  },
  {
    pattern: "packages/widgets/Build/Specs/SpecList.js",
    included: true,
    type: "module",
  },
  { pattern: "Specs/Data/**", included: false },
  { pattern: "Specs/TestWorkers/**/*.wasm", included: false },
  { pattern: "packages/engine/Build/Workers/**", included: false },
  { pattern: "packages/engine/Source/Assets/**", included: false },
  { pattern: "packages/engine/Source/ThirdParty/**", included: false },
  { pattern: "packages/engine/Source/Widget/*.css", included: false },
  { pattern: "Build/Specs/TestWorkers/**.js", included: false },
];

const proxies = {
  "/base/Build/CesiumUnminified/Assets/":
    "/base/packages/engine/Source/Assets/",
  "/base/Build/CesiumUnminified/ThirdParty/":
    "/base/packages/engine/Source/ThirdParty/",
  "/base/Build/CesiumUnminified/Widgets/CesiumWidget/":
    "/base/packages/engine/Source/Widget/",
  "/base/Build/CesiumUnminified/Workers/":
    "/base/packages/engine/Build/Workers/",
};

const config = await karma.config.parseConfig(
  karmaConfigFile,
  {
    port: 9876,
    singleRun: true,
    autoWatch: false,
    browsers: ["ChromeHeadlessNoSandbox"],
    customLaunchers: {
      ChromeHeadlessNoSandbox: {
        base: "ChromeHeadless",
        flags: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
      },
    },
    detectBrowsers: { enabled: false },
    // The repo's own karma.conf.cjs allows 120 s; on a loaded host Chromium can take longer
    // than that just to be captured, and the launcher then gives up with an EMPTY JUnit
    // report -- indistinguishable from a genuine all-red run. Be generous, but keep
    // (captureTimeout x retryLimit) x the one retry in test.sh inside the verifier's own
    // 2400 s budget.
    captureTimeout: 300000,
    browserDisconnectTimeout: 120000,
    browserDisconnectTolerance: 2,
    browserNoActivityTimeout: 300000,
    pingTimeout: 120000,
    retryLimit: 2,
    logLevel: karma.constants.LOG_ERROR,
    files: files,
    proxies: proxies,
    reporters: ["spec", "junit"],
    junitReporter: {
      outputDir: REPORT_DIR,
      outputFile: REPORT_FILE,
      useBrowserName: false,
    },
    client: {
      // Defensive, per this repo's own banked history: karma-junit-reporter buffers every
      // captured console message across the WHOLE browser session into one combined
      // <system-out> CDATA block, written once at onBrowserComplete -- a large/illegal-for-XML
      // console dump can crash the reporter before it ever writes the JUnit report, losing
      // every recorded <testcase>. This task's spec never opens WebGL / triggers a shader
      // compile at all, so this is not expected to fire, but disabling captureConsole costs
      // nothing (Jasmine's pass/fail/skip results reach the report via separate
      // specSuccess/specFailure/specSkipped events, not via console capture).
      captureConsole: false,
      // Positional args consumed by Specs/karma-main.js: [includeCategory, excludeCategory,
      // (unused "--grep" pair), webglValidation, webglStub, release, debugCanvasWidth,
      // debugCanvasHeight]. Left at the repo defaults; this spec never touches WebGL so the
      // webgl-related args are inert either way.
      args: ["", "", "--grep", "", false, false, false, undefined, undefined],
    },
  },
  { promiseConfig: true, throwErrors: true },
);

const exitCode = await new Promise((resolve) => {
  const server = new karma.Server(config, (code) => resolve(code));
  server.start();
});

console.log(`karma exit code: ${exitCode}`);
process.exit(exitCode);
