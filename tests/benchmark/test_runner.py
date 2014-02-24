# Copyright 2013: Mirantis Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock
import multiprocessing

from rally.benchmark import runner
from rally.benchmark.runners import continuous
from rally.benchmark import validation
from rally import consts
from rally import exceptions
from tests import fakes
from tests import test


def _get_fake_users(n=1):
    return [{"username": "u %s" % i, "password": "p", "tenant_name": "t",
             "auth_url": "url"} for i in range(n)]


class ScenarioRunnerTestCase(test.TestCase):

    def setUp(self):
        super(ScenarioRunnerTestCase, self).setUp()
        admin_keys = ["username", "password", "tenant_name", "auth_url"]
        endpoint_dicts = [dict(zip(admin_keys, admin_keys))]
        endpoint_dicts[0]["permission"] = consts.EndpointPermission.ADMIN
        self.fake_endpoints = endpoint_dicts

    @mock.patch("rally.benchmark.runner.base")
    @mock.patch("rally.benchmark.utils.osclients")
    def test_init_calls_register(self, mock_osclients, mock_base):
        mock_osclients.Clients.return_value = fakes.FakeClients()
        runner.ScenarioRunner.get_runner(mock.MagicMock(), self.fake_endpoints,
                                         {"execution": "continuous"})
        self.assertEqual(mock_base.mock_calls, [mock.call.Scenario.register()])

    @mock.patch("rally.benchmark.runner.rutils")
    @mock.patch("rally.benchmark.utils.osclients")
    def test_run_scenario(self, mock_osclients, mock_utils):
        mock_osclients.Clients.return_value = fakes.FakeClients()
        srunner = continuous.ContinuousScenarioRunner(mock.MagicMock(),
                                                      self.fake_endpoints)
        srunner.temp_users = _get_fake_users(5)
        active_users = 2
        times = 3
        duration = 0.01

        mock_utils.Timer = fakes.FakeTimer
        results = srunner._run_scenario(fakes.FakeScenario, "do_it", {},
                                        {"times": times,
                                         "active_users": active_users,
                                         "timeout": 2})
        expected = [{"time": 10, "idle_time": 0, "error": None,
                     "scenario_output": None, "atomic_actions_time": []}
                    for i in range(times)]
        self.assertEqual(results, expected)

        results = srunner._run_scenario(fakes.FakeScenario, "do_it", {},
                                        {"duration": duration,
                                         "active_users": active_users,
                                         "timeout": 2})
        expected = [{"time": 10, "idle_time": 0, "error": None,
                     "scenario_output": None, "atomic_actions_time": []}
                    for i in range(active_users)]
        self.assertEqual(results, expected)

    @mock.patch("rally.benchmark.utils.osclients")
    @mock.patch("multiprocessing.pool.IMapIterator.next")
    @mock.patch("rally.benchmark.runners.continuous.time.time")
    @mock.patch("rally.benchmark.utils._prepare_for_instance_ssh")
    def test_run_scenario_timeout(self, mock_prepare_for_instance_ssh,
                                  mock_time, mock_next, mock_osclients):

        mock_time.side_effect = [1, 2, 3, 10]
        mock_next.side_effect = multiprocessing.TimeoutError()
        mock_osclients.Clients.return_value = fakes.FakeClients()
        srunner = runner.ScenarioRunner.get_runner(mock.MagicMock(),
                                                   self.fake_endpoints,
                                                   {"execution": "continuous"})
        srunner.temp_users = _get_fake_users(5)
        times = 4
        active_users = 2
        results = srunner._run_scenario(fakes.FakeScenario,
                                        "too_long", {},
                                        {"times": times,
                                         "active_users": active_users,
                                         "timeout": 0.01})
        self.assertEqual(len(results), times)
        for r in results:
            self.assertEqual(r['time'], 0.01)
            self.assertEqual(r['error'][0],
                             str(multiprocessing.TimeoutError))

        duration = 0.1
        results = srunner._run_scenario(fakes.FakeScenario,
                                        "too_long", {},
                                        {"duration": duration,
                                         "active_users": active_users,
                                         "timeout": 0.01})
        self.assertEqual(len(results), active_users)
        for r in results:
            self.assertEqual(r['time'], 0.01)
            self.assertEqual(r['error'][0],
                             str(multiprocessing.TimeoutError))

    @mock.patch("rally.benchmark.runner.rutils")
    @mock.patch("rally.benchmark.utils.osclients")
    def test_run_scenario_exception_inside_test(self, mock_osclients,
                                                mock_utils):
        mock_osclients.Clients.return_value = fakes.FakeClients()
        srunner = continuous.ContinuousScenarioRunner(mock.MagicMock(),
                                                      self.fake_endpoints)
        srunner.temp_users = _get_fake_users(5)
        times = 1
        duration = 0.001
        active_users = 2

        mock_utils.Timer = fakes.FakeTimer
        results = srunner._run_scenario(fakes.FakeScenario,
                                        "something_went_wrong", {},
                                        {"times": times, "timeout": 1,
                                         "active_users": active_users})
        self.assertEqual(len(results), times)
        for r in results:
            self.assertEqual(r['time'], 10)
            self.assertEqual(r['error'][:2],
                             [str(Exception), "Something went wrong"])

        results = srunner._run_scenario(fakes.FakeScenario,
                                        "something_went_wrong", {},
                                        {"duration": duration,
                                         "timeout": 1,
                                         "active_users": active_users})
        self.assertEqual(len(results), active_users)
        for r in results:
            self.assertEqual(r['time'], 10)
            self.assertEqual(r['error'][:2],
                             [str(Exception), "Something went wrong"])

    def test_run_scenario_exception_outside_test(self):
        pass

    def _set_mocks_for_run(self, mock_osclients, mock_base, validators=None):
        FakeScenario = mock.MagicMock()
        FakeScenario.init = mock.MagicMock(return_value={})
        if validators:
            FakeScenario.do_it.validators = validators

        mock_osclients.Clients.return_value = fakes.FakeClients()
        srunner = runner.ScenarioRunner.get_runner(mock.MagicMock(),
                                                   self.fake_endpoints,
                                                   {"execution": "continuous"})
        srunner._run_scenario = mock.MagicMock(return_value="result")
        srunner.temp_users = _get_fake_users(5)

        mock_base.Scenario.get_by_name = \
            mock.MagicMock(return_value=FakeScenario)
        return FakeScenario, srunner

    @mock.patch("rally.benchmark.runner.base")
    @mock.patch("rally.benchmark.utils.osclients")
    def test_run(self, mock_osclients, mock_base):
        FakeScenario, srunner = self._set_mocks_for_run(mock_osclients,
                                                        mock_base)

        result = srunner.run("FakeScenario.do_it", {})
        self.assertEqual(result, "result")
        srunner.run("FakeScenario.do_it",
                    {"args": {"a": 1}, "init": {"arg": 1},
                     "config": {"timeout": 1, "times": 2, "active_users": 3,
                                "tenants": 5, "users_per_tenant": 2}})
        srunner.run("FakeScenario.do_it",
                    {"args": {"a": 1}, "init": {"fake": "arg"},
                     "execution_type": "continuous",
                     "config": {"timeout": 1, "duration": 40,
                                "active_users": 3, "tenants": 5,
                                "users_per_tenant": 2}})

        expected = [
            mock.call(FakeScenario, "do_it", {}, {}),
            mock.call(FakeScenario, "do_it", {"a": 1},
                      {"timeout": 1, "times": 2, "active_users": 3,
                       "tenants": 5, "users_per_tenant": 2}),
            mock.call(FakeScenario, "do_it", {"a": 1},
                      {"timeout": 1, "duration": 40, "active_users": 3,
                       "tenants": 5, "users_per_tenant": 2})
        ]
        self.assertEqual(srunner._run_scenario.mock_calls, expected)

    @mock.patch("rally.benchmark.runner.base")
    @mock.patch("rally.benchmark.utils.osclients")
    def test_run_validation_failure(self, mock_osclients, mock_base):
        def evil_validator(**kwargs):
            return validation.ValidationResult(is_valid=False)

        FakeScenario, srunner = self._set_mocks_for_run(mock_osclients,
                                                        mock_base,
                                                        [evil_validator])
        self.assertRaises(exceptions.InvalidScenarioArgument,
                          srunner.run, "FakeScenario.do_it", {})


class UserGeneratorTestCase(test.TestCase):

    @mock.patch("rally.benchmark.runner.utils.create_openstack_clients")
    def test_create_and_delete_users_and_tenants(self, mock_create_os_clients):
        return
        admin_user = {"username": "admin", "password": "pwd",
                      "tenant_name": "admin", "auth_url": "url"}
        created_users = []
        created_tenants = []
        with runner.UserGenerator(admin_user) as generator:
            tenants = 10
            users_per_tenant = 5
            endpoints = generator.create_users_and_tenants(tenants,
                                                           users_per_tenant)
            self.assertEqual(len(endpoints), tenants * users_per_tenant)
            created_users = generator.users
            created_tenants = generator.tenants
        self.assertTrue(all(u.status == "DELETED" for u in created_users))
        self.assertTrue(all(t.status == "DELETED" for t in created_tenants))


class ResourceCleanerTestCase(test.TestCase):

    def test_with_statement_no_user_no_admin(self):
        resource_cleaner = runner.ResourceCleaner()
        with resource_cleaner:
            pass

    def test_with_statement(self):
        res_cleaner = runner.ResourceCleaner()
        res_cleaner._cleanup_users_resources = mock.MagicMock()
        res_cleaner._cleanup_admin_resources = mock.MagicMock()

        with res_cleaner as cleaner:
            self.assertEqual(res_cleaner, cleaner)

        res_cleaner._cleanup_users_resources.assert_called_once_with()
        res_cleaner._cleanup_admin_resources.assert_called_once_with()

    @mock.patch("rally.benchmark.runner.utils.create_openstack_clients")
    @mock.patch("rally.benchmark.runner.utils.delete_keystone_resources")
    def test_cleaner_admin(self, mock_del_keystone, mock_create_os_clients):

        admin_endpoit = "admin"
        res_cleaner = runner.ResourceCleaner(admin=admin_endpoit)

        admin_client = mock.MagicMock()
        admin_client.__getitem__ = mock.MagicMock(return_value="keystone_cl")
        mock_create_os_clients.return_value = admin_client

        with res_cleaner:
            pass

        mock_create_os_clients.assert_called_once_with(admin_endpoit)
        admin_client.__getitem__.assert_called_once_with("keystone")
        mock_del_keystone.assert_called_once_with("keystone_cl")

    @mock.patch("rally.benchmark.runner.utils.create_openstack_clients")
    @mock.patch("rally.benchmark.runner.utils.delete_nova_resources")
    @mock.patch("rally.benchmark.runner.utils.delete_glance_resources")
    @mock.patch("rally.benchmark.runner.utils.delete_cinder_resources")
    def test_cleaner_users(self, mock_del_cinder, mock_del_glance,
                           mock_del_keystone, mock_create_os_clients):

        res_cleaner = runner.ResourceCleaner(users=["user1", "user2"])

        client = mock.MagicMock()
        mock_create_os_clients.return_value = client

        with res_cleaner:
            pass