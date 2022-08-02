# Copyright 2018, OpenCensus Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import random
import sys
import time

import mock
from google.cloud import monitoring_v3

from opencensus.ext.stackdriver import stats_exporter as stackdriver
from opencensus.metrics import transport
from opencensus.stats import aggregation as aggregation_module
from opencensus.stats import measure as measure_module
from opencensus.stats import stats as stats_module
from opencensus.stats import view as view_module
from opencensus.tags import tag_key as tag_key_module
from opencensus.tags import tag_map as tag_map_module
from opencensus.tags import tag_value as tag_value_module

if sys.version_info < (3,):
    import unittest2 as unittest
else:
    import unittest


MiB = 1 << 20

PROJECT = os.environ.get('GCLOUD_PROJECT_PYTHON')
ASYNC_TEST_INTERVAL = 15  # Background thread export interval


class TestBasicStats(unittest.TestCase):

    def check_sd_md(self, exporter, view_description):
        """Check that the metric descriptor was written to stackdriver."""
        name = exporter.client.common_project_path(PROJECT)
        list_metrics_descriptors = exporter.client.list_metric_descriptors(
            name)

        for ee in list_metrics_descriptors:
            if ee.description == view_description:
                break
        else:
            raise AssertionError("No matching metric descriptor")

        self.assertIsNotNone(ee)
        self.assertEqual(ee.unit, "By")

    def setUp(self):
        patcher = mock.patch(
            'opencensus.ext.stackdriver.stats_exporter.stats.stats',
            stats_module._Stats())
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        suffix = str(os.getgid())

        cli = monitoring_v3.MetricServiceClient()
        for md in cli.list_metric_descriptors(f'projects/{PROJECT}'):
            if "OpenCensus" in md.name and suffix in md.name:
                try:
                    cli.delete_metric_descriptor(md.name)
                except Exception:
                    pass

    def test_stats_record_sync(self):
        # We are using suffix in order to prevent cached objects
        suffix = str(os.getgid())

        tag_key = f"SampleKeySyncTest{suffix}"
        measure_name = f"SampleMeasureNameSyncTest{suffix}"
        measure_description = f"SampleDescriptionSyncTest{suffix}"
        view_name = f"SampleViewNameSyncTest{suffix}"
        view_description = f"SampleViewDescriptionSyncTest{suffix}"

        FRONTEND_KEY = tag_key_module.TagKey(tag_key)
        VIDEO_SIZE_MEASURE = measure_module.MeasureInt(
            measure_name, measure_description, "By")
        VIDEO_SIZE_VIEW_NAME = view_name
        VIDEO_SIZE_DISTRIBUTION = aggregation_module.DistributionAggregation(
            [0.0, 16.0 * MiB, 256.0 * MiB])
        VIDEO_SIZE_VIEW = view_module.View(
            VIDEO_SIZE_VIEW_NAME, view_description, [FRONTEND_KEY],
            VIDEO_SIZE_MEASURE, VIDEO_SIZE_DISTRIBUTION)

        stats = stats_module.stats
        view_manager = stats.view_manager
        stats_recorder = stats.stats_recorder

        client = monitoring_v3.MetricServiceClient()
        exporter = stackdriver.StackdriverStatsExporter(
            options=stackdriver.Options(project_id=PROJECT),
            client=client)
        view_manager.register_exporter(exporter)

        # Register view.
        view_manager.register_view(VIDEO_SIZE_VIEW)

        # Sleep for [0, 10] milliseconds to fake work.
        time.sleep(random.randint(1, 10) / 1000.0)

        # Process video.
        # Record the processed video size.
        tag_value = tag_value_module.TagValue("1200")
        tag_map = tag_map_module.TagMap()
        tag_map.insert(FRONTEND_KEY, tag_value)
        measure_map = stats_recorder.new_measurement_map()
        measure_map.measure_int_put(VIDEO_SIZE_MEASURE, 25 * MiB)

        measure_map.record(tag_map)
        exporter.export_metrics(stats_module.stats.get_metrics())

        # Sleep for [0, 10] milliseconds to fake wait.
        time.sleep(random.randint(1, 10) / 1000.0)

        self.check_sd_md(exporter, view_description)

    def test_stats_record_async(self):
        # We are using suffix in order to prevent cached objects
        suffix = str(os.getpid())

        tag_key = f"SampleKeyAsyncTest{suffix}"
        measure_name = f"SampleMeasureNameAsyncTest{suffix}"
        measure_description = f"SampleDescriptionAsyncTest{suffix}"
        view_name = f"SampleViewNameAsyncTest{suffix}"
        view_description = f"SampleViewDescriptionAsyncTest{suffix}"

        FRONTEND_KEY_ASYNC = tag_key_module.TagKey(tag_key)
        VIDEO_SIZE_MEASURE_ASYNC = measure_module.MeasureInt(
            measure_name, measure_description, "By")
        VIDEO_SIZE_VIEW_NAME_ASYNC = view_name
        VIDEO_SIZE_DISTRIBUTION_ASYNC =\
                aggregation_module.DistributionAggregation(
                [0.0, 16.0 * MiB, 256.0 * MiB]
            )
        VIDEO_SIZE_VIEW_ASYNC = view_module.View(
            VIDEO_SIZE_VIEW_NAME_ASYNC, view_description, [FRONTEND_KEY_ASYNC],
            VIDEO_SIZE_MEASURE_ASYNC, VIDEO_SIZE_DISTRIBUTION_ASYNC)

        stats = stats_module.stats
        view_manager = stats.view_manager
        stats_recorder = stats.stats_recorder

        exporter = stackdriver.new_stats_exporter(
            stackdriver.Options(project_id=PROJECT))
        view_manager.register_exporter(exporter)

        # Register view.
        view_manager.register_view(VIDEO_SIZE_VIEW_ASYNC)

        # Sleep for [0, 10] milliseconds to fake work.
        time.sleep(random.randint(1, 10) / 1000.0)

        # Process video.
        # Record the processed video size.
        tag_value = tag_value_module.TagValue("1200")
        tag_map = tag_map_module.TagMap()
        tag_map.insert(FRONTEND_KEY_ASYNC, tag_value)
        measure_map = stats_recorder.new_measurement_map()
        measure_map.measure_int_put(VIDEO_SIZE_MEASURE_ASYNC, 25 * MiB)

        measure_map.record(tag_map)
        # Give the exporter thread enough time to export exactly once
        time.sleep(transport.DEFAULT_INTERVAL * 1.5)

        self.check_sd_md(exporter, view_description)
