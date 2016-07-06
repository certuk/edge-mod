// Learn more about configuring this file at <https://theintern.github.io/intern/#configuration>.
// These default settings work OK for most people. The options that *must* be changed below are the
// packages, suites, excludeInstrumentation, and (if you want functional tests) functionalSuites
define({
    // Default desired capabilities for all environments. Individual capabilities can be overridden by any of the
    // specified browser environments in the `environments` array below as well. See
    // <https://theintern.github.io/intern/#option-capabilities> for links to the different capabilities options for
    // different services.
    //
    // Note that the `build` capability will be filled in with the current commit ID or build tag from the CI
    // environment automatically
    capabilities: {
        "browserstack.selenium_version": "2.45.0"
    },

    // Browsers to run integration testing against. Note that version numbers must be strings if used with Sauce
    // OnDemand. Options that will be permutated are browserName, version, platform, and platformVersion; any other
    // capabilities options specified for an environment will be copied as-is
    environments: [
        /*
         {browserName: "internet explorer", version: "11", platform: "WIN8"},
         {browserName: "internet explorer", version: "10", platform: "WIN8"},
         {browserName: "internet explorer", version: "9", platform: "WINDOWS"},
         {browserName: "firefox", version: "37", platform: ["WINDOWS", "MAC"]},
         {browserName: "chrome", version: "39", platform: ["WINDOWS", "MAC"]},
         {browserName: "safari", version: "8", platform: "MAC"}
         */
    ],

    // Maximum number of simultaneous integration tests that should be executed on the remote WebDriver service
    maxConcurrency: 2,

    // Name of the tunnel class to use for WebDriver tests.
    // See <https://theintern.github.io/intern/#option-tunnel> for built-in options
    tunnel: "NullTunnel",

    // Configuration options for the module loader; any AMD configuration options supported by the AMD loader in use
    // can be used here.
    // If you want to use a different loader than the default loader, see
    // <https://theintern.github.io/intern/#option-useLoader> for instruction
    loaderOptions: {
        // Packages that should be registered with the loader in each testing environment
        packages: [
            {name: "config-service", location: "static/js/common/tests/unit", main: "mock-config.json"},
            {name: "ind-build", location: "static/js/ind-build"},
            {name: "inc-build", location: "static/js/inc-build"},
            {name: "timeline", location: "static/js/timeline"},
            {name: "common", location: "static/js/common"},
            {name: "dcl", location: "static/js/dcl"},
            {name: "knockout", location: "tests/support", main: "knockout-3.1.0.debug"},
            {name: "d3", location: "tests/support", main: "d3"},
            {name: "kotemplate", location: "static/js", main: "kotemplate"},
            {name: "publisher", location: "static/js/publisher"},
            {name: "stix", location: "static/js/stix"},
            {name: "text", location: "static/js", main: "text"}
        ]
    },

    // Non-functional test suite(s) to run in each browser
    suites: [
        "tests/unit/all"
    ],

    // Functional test suite(s) to execute against each browser once non-functional tests are completed
    functionalSuites: [/* "myPackage/tests/functional" */],

    // A regular expression matching URLs to files that should not be included in code coverage analysis
    excludeInstrumentation: /(?:(?:tests|node_modules|dcl)\/|js\/(?:kotemplate|text).js$)/,

    reporters: [
        {id: "JUnit", filename: "tests/junit.xml"},
        {id: "Cobertura", filename: "tests/cobertura.xml"}
    ]
});
