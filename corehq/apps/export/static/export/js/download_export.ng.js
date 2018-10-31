(function (angular, undefined) {
    'use strict';
    // module: hq.download_export

    /* This is the helper module for the Download Exports Page. */

    var download_export = angular.module('hq.download_export', [
        'ngResource',
        'ngRoute',
        'ng.django.rmi',
        'ngMessages',
    ]);

    download_export.config(['$httpProvider', function ($httpProvider) {
        $httpProvider.defaults.headers.common['X-Requested-With'] = 'XMLHttpRequest';
        $httpProvider.defaults.xsrfCookieName = 'csrftoken';
        $httpProvider.defaults.xsrfHeaderName = 'X-CSRFToken';
        $httpProvider.defaults.headers.common["X-CSRFToken"] = $("#csrfTokenContainer").val();
    }]);
    download_export.constant('formElement', {
        progress: function () { return null; },
        group: function () { return null; },
        user_type: function () { return null; },
    });

    download_export.constant('exportList', []);
    download_export.constant('maxColumnSize', 2000);
    download_export.constant('defaultDateRange', null);
    download_export.constant('checkForMultimedia', false);

    var exportsControllers = {};
    exportsControllers.DownloadExportFormController = function (
        $scope, djangoRMI, exportList, maxColumnSize, exportDownloadService,
        defaultDateRange, checkForMultimedia, formElement
    ) {
        var self = {};
        $scope._ = _;   // make underscore.js available
        self._maxColumnSize = maxColumnSize;
        $scope.formData = {};
        $scope.exportList = _.map(exportList, function (exportData) {
            exportData.filename = encodeURIComponent(exportData.name);
            return exportData;
        });

        $scope.hasMultimedia = false;
        if (checkForMultimedia) {
            djangoRMI.has_multimedia({})
                .success(function (data) {
                    if (data.success) {
                        $scope.hasMultimedia = data.hasMultimedia;
                    }
                });
        }

        $scope.formData.user_types = ['mobile'];
        $scope.formData['emw'] = hqImport('reports/js/reports.util').urlSerialize(
            $('form[name="exportFiltersForm"]'));
        if (formElement.user_type()) formElement.user_type().select2('val', ['mobile']);

        if (!_.isNull(defaultDateRange)) {
            $scope.formData.date_range = defaultDateRange;
        }

        $scope.preparingExport = false;

        $scope.prepareExportError = null;

        var exportType = $scope.exportList[0].export_type;
        self.exportType = hqImport('export/js/utils').capitalize(exportType);
        if (exportType === 'case') {
            self.has_case_history_table = _.any($scope.exportList, function (export_) {
                return export_.has_case_history_table;
            });
        }

        self.sendAnalytics = function () {
            _.each($scope.formData.user_types, function (user_type) {
                hqImport('analytix/js/google').track.event("Download Export", 'Select "user type"', user_type);
            });
            var action = ($scope.exportList.length > 1) ? "Bulk" : "Regular";
            hqImport('analytix/js/google').track.event("Download Export", self.exportType, action);
            if (self.has_case_history_table) {
                _.each($scope.exportList, function (export_) {
                    if (export_.has_case_history_table) {
                        hqImport('analytix/js/google').track.event("Download Case History Export", export_.domain, export_.export_id);
                    }
                });
            }
        };

        $scope.isFormInvalid = function () {
            return _.isEmpty($scope.formData.user_types);
        };

        $scope.prepareExport = function () {
            $scope.formData['emw'] = hqImport('reports/js/reports.util').urlSerialize(
                $('form[name="exportFiltersForm"]'));
            $scope.prepareExportError = null;
            $scope.preparingExport = true;
            var userTypes = hqImport("hqwebapp/js/initial_page_data").get('user_types');
            function getFilterName(exportType) {
                return (exportType === "form" ? "emw" : "case_list_filter");
            }

            var filterNamesAsString = $("#exportFiltersFormId").find("input[name="
                        + getFilterName($scope.exportList[0].export_type) + "]")
                .val();

            function getFilterNames() {
                return (filterNamesAsString ? filterNamesAsString.split(',') : []);
            }

            hqImport('analytix/js/kissmetrix').track.event("Clicked Prepare Export", {
                "Export type": $scope.exportList[0].export_type,
                "filters": _.map(
                    getFilterNames(),
                    function (item) {
                        var prefix = "t__";
                        if (item.substring(0, prefix.length) === prefix) {
                            return userTypes[item.substring(prefix.length)];
                        }
                        return item;
                    }
                ).join()});
            djangoRMI.prepare_custom_export({
                exports: $scope.exportList,
                max_column_size: self._maxColumnSize,
                form_data: $scope.formData,
            })
                .success(function (data) {
                    if (data.success) {
                        self.sendAnalytics();
                        $scope.preparingExport = false;
                        $scope.downloadInProgress = true;
                        exportDownloadService.startDownload(data.download_id, self.exportType);
                    } else {
                        self._handlePrepareError(data);
                    }
                })
                .error(self._handlePrepareError);
        };

        self._handlePrepareError = function (data) {
            if (data && data.error) {
                // The server returned an error message.
                $scope.prepareExportError = data.error;
            } else {
                $scope.prepareExportError = "default";
            }
            $scope.preparingExport = false;
            $scope.preparingMultimediaExport = false;
        };

        $scope.preparingMultimediaExport = false;
        $scope.prepareMultimediaExport = function () {
            $scope.prepareExportError = null;
            $scope.preparingMultimediaExport = true;
            djangoRMI.prepare_form_multimedia({
                exports: $scope.exportList,
                form_data: $scope.formData,
            })
                .success(function (data) {
                    if (data.success) {
                        self.sendAnalytics();
                        $scope.preparingMultimediaExport = false;
                        $scope.downloadInProgress = true;
                        exportDownloadService.startMultimediaDownload(data.download_id, self.exportType);
                    } else {
                        self._handlePrepareError(data);
                    }
                })
                .error(self._handlePrepareError);
        };

        $scope.$watch(function () {
            return exportDownloadService.showDownloadStatus;
        }, function (status) {
            $scope.downloadInProgress = status;
        });
        $scope.downloadInProgress = false;
    };

    exportsControllers.DownloadProgressController = function (
        $scope, exportDownloadService, formElement
    ) {
        var self = {};

        self._reset = function () {
            $scope.showProgress = false;
            $scope.showDownloadStatus = false;
            $scope.isDownloadReady = false;
            $scope.isDownloaded = false;
            $scope.dropboxUrl = null;
            $scope.downloadUrl = null;
            $scope.progress = {};
            $scope.showError = false;
            $scope.celeryError = false;
            $scope.downloadError = false;
            $scope.isMultimediaDownload = false;
            if (formElement.progress()) {
                formElement.progress().css('width', '0%');
                formElement.progress().removeClass('progress-bar-success');
            }
        };

        self._reset();

        $scope.$watch(function () {
            return exportDownloadService.downloadStatusData;
        }, function (data) {
            if (!_.isEmpty(data)) {
                $scope.progress = data.progress;
                self._updateProgressBar(data);
                $scope.download_id = data.download_id;
                $scope.showProgress = true;
            }
        });

        self._updateProgressBar = function (data) {
            var progressPercent = 0;
            if (data.is_ready && data.has_file) {
                progressPercent = 100;
                $scope.isDownloadReady = true;
                $scope.dropboxUrl = data.dropbox_url;
                $scope.downloadUrl = data.download_url;
                if (formElement.progress()) formElement.progress().addClass('progress-bar-success');
            } else if (_.isNumber(data.progress.percent)) {
                progressPercent = data.progress.percent;
            }
            $scope.progress.percent = progressPercent;
            if (formElement.progress()) formElement.progress().css('width', progressPercent + '%');
        };

        $scope.resetDownload = function () {
            self._reset();
            exportDownloadService.resetDownload();
        };

        $scope.$watch(function () {
            return exportDownloadService.showDownloadStatus;
        }, function (status) {
            $scope.showDownloadStatus = status;
        });

        $scope.$watch(function () {
            return exportDownloadService.celeryError;
        }, function (status) {
            $scope.celeryError = status;
            $scope.showError = status;
        });

        $scope.$watch(function () {
            return exportDownloadService.downloadError;
        }, function (status) {
            $scope.downloadError = status;
            $scope.showError = status;
        });

        $scope.$watch(function () {
            return exportDownloadService.isMultimediaDownload;
        }, function (status) {
            $scope.isMultimediaDownload = status;
        });

        $scope.sendAnalytics = function () {
            hqImport('analytix/js/google').track.event(
                "Download Export",
                hqImport('export/js/utils').capitalize(exportDownloadService.exportType), "Saved");
            hqImport('analytix/js/kissmetrix').track.event("Clicked Download button");
        };

        $scope.sendEmailUponCompletion = function () {
            setTimeout(function () {  // function must wait until download_id is available in the scope
                if ($scope.download_id !== undefined) {
                    var initial_page_data = hqImport('hqwebapp/js/initial_page_data');
                    $.ajax({
                        method: 'POST',
                        dataType: 'json',
                        url: initial_page_data.reverse('add_export_email_request'),
                        data: { download_id: $scope.download_id },
                    });
                } else {
                    $scope.sendEmailUponCompletion();
                }
            });
        };
    };
    download_export.controller(exportsControllers);

    var downloadExportServices = {};
    downloadExportServices.exportDownloadService = function ($interval, djangoRMI) {
        var self = {};

        self.resetDownload = function () {
            self.downloadId = null;
            self._numErrors = 0;
            self._numCeleryRetries = 0;
            self._lastProgress = 0;
            self.downloadStatusData = null;
            self.showDownloadStatus = false;
            self.downloadError = null;
            self.celeryError = false;
            self.downloadError = false;
            self.isMultimediaDownload = false;
            self.exportType = null;
        };

        self.resetDownload();

        self._checkDownloadProgress = function () {
            djangoRMI.poll_custom_export_download({
                download_id: self.downloadId,
            })
                .success(function (data) {
                    if (data.is_poll_successful) {
                        self.downloadStatusData = data;
                        if (data.has_file && data.is_ready) {
                            $interval.cancel(self._promise);
                            return;
                        }
                        if (data.progress && data.progress.error) {
                            $interval.cancel(self._promise);
                            self.downloadError = data.progress.error;
                            return;
                        }
                        if (data.progress.current > self._lastProgress) {
                            self._lastProgress = data.progress.current;
                            // processing is still going, keep moving.
                            // this avoids failing hard prematurely at celery errors if
                            // the polling is still reporting forward progress.
                            self._numCeleryRetries = 0;
                            return;
                        }
                    }
                    if (data.error) {
                        self._dealWithErrors(data);
                    }
                    if (_.isNull(data.is_alive)) {
                        self._dealWithCeleryErrors();
                    }
                })
                .error(self._dealWithErrors);
        };

        self._dealWithCeleryErrors = function () {
            // Sometimes the task handler for celery is a little slow to get
            // started, so we have to try a few times.
            if (self._numCeleryRetries > 10) {
                $interval.cancel(self._promise);
                self.celeryError = true;
            }
            self._numCeleryRetries ++;
        };

        self._dealWithErrors = function (data) {
            if (self._numErrors > 3) {
                if (data && data.error) {
                    self.downloadError = data.error;
                } else {
                    self.downloadError = "default";
                }
                $interval.cancel(self._promise);
            }
            self._numErrors ++;
        };

        self.startDownload = function (downloadId, exportType) {
            self.showDownloadStatus = true;
            self.downloadId = downloadId;
            self.exportType = exportType;
            self._promise = $interval(self._checkDownloadProgress, 2000);
        };

        self.startMultimediaDownload = function (downloadId, exportType) {
            self.isMultimediaDownload = true;
            self.startDownload(downloadId, exportType);
        };

        return self;
    };
    download_export.factory(downloadExportServices);

}(window.angular));