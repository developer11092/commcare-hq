/* globals requirejs */
requirejs.config({
    baseUrl: '/static/',
    paths: {
        'jquery': 'jquery/dist/jquery.min',
        'underscore': 'underscore/underscore',
        'bootstrap': 'bootstrap/dist/js/bootstrap.min',
        'knockout': 'knockout/dist/knockout.debug',
        'ko.mapping': 'hqwebapp/js/lib/knockout_plugins/knockout_mapping.ko.min',
        'datatables': 'datatables/media/js/jquery.dataTables.min',
        'datatables.fixedColumns': 'datatables-fixedcolumns/js/dataTables.fixedColumns',
        'datatables.bootstrap': 'datatables-bootstrap3/BS3/assets/js/datatables',
    },
    shim: {
        'ace-builds/src-min-noconflict/ace': { exports: 'ace' },
        'blazy/blazy': { exports: 'Blazy' },
        'bootstrap': { deps: ['jquery'] },
        'bootstrap-timepicker/js/bootstrap-timepicker': { deps: ['bootstrap'] },
        'datatables.bootstrap': { deps: ['datatables'] },
        'datatables.fixedColumns': { deps: ['datatables'] },
        'hqwebapp/js/hq.helpers': { deps: ['jquery', 'bootstrap', 'knockout', 'underscore'] },
        'hqwebapp/js/hq_extensions.jquery': { deps: ['jquery'] },
        'hqwebapp/js/knockout_bindings.ko': { deps: ['knockout'] },
        'hqwebapp/js/password_validators.ko': { deps: ['knockout', 'knockout-validation/dist/knockout.validation.min'] },
        'hqwebapp/js/validators.ko': { deps: ['knockout', 'knockout-validation/dist/knockout.validation.min'] },
        'intl-tel-input/build/js/intlTelInput.min': { deps: ['jquery'] },
        'jquery.cookie/jquery.cookie': { deps: ['jquery'] },
        'jquery-form/dist/jquery.form.min': { deps: ['jquery'] },
        'jquery-memoized-ajax/jquery.memoized.ajax.min': { deps: ['jquery'] },
        'jquery.rmi/jquery.rmi': {
            deps: ['jquery', 'knockout', 'underscore'],
            exports: 'RMI',
        },
        'jquery-treetable/jquery.treetable': { deps: ['jquery'] },
        'jquery-ui/ui/datepicker': { deps: ['jquery'] },
        'jquery-ui/ui/effect': { deps: ['jquery'] },
        'jquery-ui/ui/effect-slide': { deps: ['jquery', 'jquery-ui/ui/effect'] },
        'ko.mapping': { deps: ['knockout'] },
        'knockout-validation/dist/knockout.validation.min': { deps: ['knockout'] },
        'multiselect/js/jquery.multi-select': { deps: ['jquery'] },
        'quicksearch/dist/jquery.quicksearch.min': { deps: ['jquery'] },
        'nvd3/nv.d3.min':{deps:['d3/d3.min']},
        'accounting/js/lib/stripe': {
            exports: 'Stripe',
        },
    },
    map: {
        'datatables.fixedColumns': {
            'datatables.net': 'datatables',
        },
    },

    // This is really build config, but it's easier to define a js function here than in requirejs.yaml
    onBuildRead: function (moduleName, path, contents) {
        return contents.replace(/hqDefine/g, 'define');
    },
});
