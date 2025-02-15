import json
import tempfile
from collections import OrderedDict
from unittest import TestCase

from unittest.mock import ANY, patch, Mock
from parameterized import parameterized

from samcli.commands.validate.lib.exceptions import InvalidSamDocumentException
from samcli.lib.providers.api_provider import ApiProvider
from samcli.lib.providers.provider import Cors, Stack
from samcli.lib.providers.sam_api_provider import SamApiProvider
from samcli.local.apigw.route import Route
from samcli.local.apigw.authorizers.lambda_authorizer import LambdaAuthorizer


def make_mock_stacks_from_template(template):
    stack_mock = Stack("", "", Mock(), parameters=None, template_dict=template)
    return [stack_mock]


class TestSamApiProviderWithImplicitApis(TestCase):
    def test_provider_with_no_resource_properties(self):
        template = {"Resources": {"SamFunc1": {"Type": "AWS::Lambda::Function"}}}

        provider = ApiProvider(make_mock_stacks_from_template(template))

        self.assertEqual(provider.routes, [])

    @parameterized.expand([("GET"), ("get")])
    def test_provider_has_correct_api(self, method):
        template = {
            "Resources": {
                "SamFunc1": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {
                        "CodeUri": "/usr/foo/bar",
                        "Runtime": "nodejs4.3",
                        "Handler": "index.handler",
                        "Events": {"Event1": {"Type": "Api", "Properties": {"Path": "/path", "Method": method}}},
                    },
                }
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        self.assertEqual(len(provider.routes), 1)
        self.assertEqual(list(provider.routes)[0], Route(path="/path", methods=["GET"], function_name="SamFunc1"))

    def test_provider_creates_api_for_all_events(self):
        template = {
            "Resources": {
                "SamFunc1": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {
                        "CodeUri": "/usr/foo/bar",
                        "Runtime": "nodejs4.3",
                        "Handler": "index.handler",
                        "Events": {
                            "Event1": {"Type": "Api", "Properties": {"Path": "/path", "Method": "GET"}},
                            "Event2": {"Type": "Api", "Properties": {"Path": "/path", "Method": "POST"}},
                        },
                    },
                }
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        api = Route(path="/path", methods=["GET", "POST"], function_name="SamFunc1")

        self.assertIn(api, provider.routes)
        self.assertEqual(len(provider.routes), 1)

    def test_provider_has_correct_template(self):
        template = {
            "Resources": {
                "SamFunc1": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {
                        "CodeUri": "/usr/foo/bar",
                        "Runtime": "nodejs4.3",
                        "Handler": "index.handler",
                        "Events": {"Event1": {"Type": "Api", "Properties": {"Path": "/path", "Method": "GET"}}},
                    },
                },
                "SamFunc2": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {
                        "CodeUri": "/usr/foo/bar",
                        "Runtime": "nodejs4.3",
                        "Handler": "index.handler",
                        "Events": {"Event1": {"Type": "Api", "Properties": {"Path": "/path", "Method": "POST"}}},
                    },
                },
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        api1 = Route(path="/path", methods=["GET"], function_name="SamFunc1")
        api2 = Route(path="/path", methods=["POST"], function_name="SamFunc2")

        self.assertIn(api1, provider.routes)
        self.assertIn(api2, provider.routes)

    def test_provider_with_no_api_events(self):
        template = {
            "Resources": {
                "SamFunc1": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {
                        "CodeUri": "/usr/foo/bar",
                        "Runtime": "nodejs4.3",
                        "Handler": "index.handler",
                        "Events": {"Event1": {"Type": "S3", "Properties": {"Property1": "value"}}},
                    },
                }
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        self.assertEqual(provider.routes, [])

        template1 = {
            "Resources": {
                "Go1xFunction": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {
                        "CodeUri": "./go1.x/main.zip",
                        "Runtime": "go1.x",
                        "Handler": "main",
                        "Timeout": 300,
                    },
                }
            }
        }

        provider1 = ApiProvider(make_mock_stacks_from_template(template))

        self.assertEqual(provider1.routes, [])

    def test_provider_with_no_serverless_function(self):
        template = {
            "Resources": {
                "SamFunc1": {
                    "Type": "AWS::Lambda::Function",
                    "Properties": {"CodeUri": "/usr/foo/bar", "Runtime": "nodejs4.3", "Handler": "index.handler"},
                }
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        self.assertEqual(provider.routes, [])

    def test_provider_get_all(self):
        template = {
            "Resources": {
                "SamFunc1": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {
                        "CodeUri": "/usr/foo/bar",
                        "Runtime": "nodejs4.3",
                        "Handler": "index.handler",
                        "Events": {"Event1": {"Type": "Api", "Properties": {"Path": "/path", "Method": "GET"}}},
                    },
                },
                "SamFunc2": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {
                        "CodeUri": "/usr/foo/bar",
                        "Runtime": "nodejs4.3",
                        "Handler": "index.handler",
                        "Events": {"Event1": {"Type": "Api", "Properties": {"Path": "/path", "Method": "POST"}}},
                    },
                },
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        result = [f for f in provider.get_all()]
        routes = result[0].routes
        route1 = Route(path="/path", methods=["GET"], function_name="SamFunc1")
        route2 = Route(path="/path", methods=["POST"], function_name="SamFunc2")

        self.assertIn(route1, routes)
        self.assertIn(route2, routes)

    def test_provider_get_all_with_no_routes(self):
        template = {}

        provider = ApiProvider(make_mock_stacks_from_template(template))

        result = [f for f in provider.get_all()]
        routes = result[0].routes

        self.assertEqual(routes, [])

    @parameterized.expand([("ANY"), ("any")])
    def test_provider_with_any_method(self, method):
        template = {
            "Resources": {
                "SamFunc1": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {
                        "CodeUri": "/usr/foo/bar",
                        "Runtime": "nodejs4.3",
                        "Handler": "index.handler",
                        "Events": {"Event1": {"Type": "Api", "Properties": {"Path": "/path", "Method": method}}},
                    },
                }
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        api1 = Route(
            path="/path", methods=["GET", "DELETE", "PUT", "POST", "HEAD", "OPTIONS", "PATCH"], function_name="SamFunc1"
        )

        self.assertEqual(len(provider.routes), 1)
        self.assertIn(api1, provider.routes)

    def test_provider_must_support_binary_media_types(self):
        template = {
            "Globals": {
                "Api": {"BinaryMediaTypes": ["image~1gif", "image~1png", "image~1png"]}  # Duplicates must be ignored
            },
            "Resources": {
                "SamFunc1": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {
                        "CodeUri": "/usr/foo/bar",
                        "Runtime": "nodejs4.3",
                        "Handler": "index.handler",
                        "Events": {"Event1": {"Type": "Api", "Properties": {"Path": "/path", "Method": "get"}}},
                    },
                }
            },
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        self.assertEqual(len(provider.routes), 1)
        self.assertEqual(list(provider.routes)[0], Route(path="/path", methods=["GET"], function_name="SamFunc1"))

        self.assertCountEqual(provider.api.binary_media_types, ["image/gif", "image/png"])
        self.assertEqual(provider.api.stage_name, "Prod")

    def test_provider_must_support_binary_media_types_with_any_method(self):
        template = {
            "Globals": {"Api": {"BinaryMediaTypes": ["image~1gif", "image~1png", "text/html"]}},
            "Resources": {
                "SamFunc1": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {
                        "CodeUri": "/usr/foo/bar",
                        "Runtime": "nodejs4.3",
                        "Handler": "index.handler",
                        "Events": {"Event1": {"Type": "Api", "Properties": {"Path": "/path", "Method": "any"}}},
                    },
                }
            },
        }

        binary = ["image/gif", "image/png", "text/html"]

        expected_routes = [
            Route(
                path="/path",
                methods=["GET", "DELETE", "PUT", "POST", "HEAD", "OPTIONS", "PATCH"],
                function_name="SamFunc1",
            )
        ]

        provider = ApiProvider(make_mock_stacks_from_template(template))

        self.assertCountEqual(provider.routes, expected_routes)
        self.assertCountEqual(provider.api.binary_media_types, binary)

    @parameterized.expand([("GET", "/path", "overridden_by_top_level_stack"), ("get", "/path2", False)])
    def test_provider_with_multiple_stacks(self, method, func2_api_path, overridden_by_top_level_stack):
        """
        Here we test func2 has the same path & method and different path/method
        """
        template = {
            "Resources": {
                "SamFunc1": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {
                        "CodeUri": "/usr/foo/bar",
                        "Runtime": "nodejs4.3",
                        "Handler": "index.handler",
                        "Events": {"Event1": {"Type": "Api", "Properties": {"Path": "/path", "Method": method}}},
                    },
                }
            }
        }

        child_template = {
            "Resources": {
                "SamFunc2": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {
                        "CodeUri": "/usr/foo/bar",
                        "Runtime": "nodejs4.3",
                        "Handler": "index.handler",
                        "Events": {
                            "Event1": {"Type": "Api", "Properties": {"Path": func2_api_path, "Method": "GET"}},
                            "Event2": {
                                "Type": "Api",
                                "Properties": {"Path": func2_api_path, "Method": "POST"},
                            },
                        },
                    },
                }
            }
        }

        child_stack = Stack("", "ChildStackX", Mock(), None, child_template)
        stacks = make_mock_stacks_from_template(template)
        stacks.append(child_stack)
        provider = ApiProvider(stacks)

        self.assertEqual(len(provider.routes), 2)
        self.assertSetEqual(
            set(provider.routes),
            {
                Route(path="/path", methods=["GET"], function_name="SamFunc1"),
                Route(
                    path=func2_api_path,
                    # if func2's API also has the path "/path," func1's "/path:GET" should
                    # have a higher precedence, while func2's "/path:POST" still survive
                    methods=["POST"] if overridden_by_top_level_stack else ["GET", "POST"],
                    function_name="SamFunc2",
                    stack_path="ChildStackX",
                ),
            },
        )


class TestSamApiProviderWithExplicitApis(TestCase):
    def setUp(self):
        self.binary_types = ["image/png", "image/jpg"]
        self.stage_name = "Prod"
        self.input_routes = [
            Route(path="/path1", methods=["GET", "POST"], function_name="SamFunc1"),
            Route(path="/path2", methods=["PUT", "GET"], function_name="SamFunc1"),
            Route(path="/path3", methods=["DELETE"], function_name="SamFunc1"),
        ]

    def test_with_no_routes(self):
        template = {"Resources": {"Api1": {"Type": "AWS::Serverless::Api", "Properties": {"StageName": "Prod"}}}}

        provider = ApiProvider(make_mock_stacks_from_template(template))

        self.assertEqual(provider.routes, [])

    def test_with_inline_swagger_routes(self):
        template = {
            "Resources": {
                "Api1": {
                    "Type": "AWS::Serverless::Api",
                    "Properties": {"StageName": "Prod", "DefinitionBody": make_swagger(self.input_routes)},
                }
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))
        self.assertCountEqual(self.input_routes, provider.routes)

    def test_with_swagger_as_local_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as fp:
            filename = fp.name

            swagger = make_swagger(self.input_routes)
            json.dump(swagger, fp)
            fp.flush()

            template = {
                "Resources": {
                    "Api1": {
                        "Type": "AWS::Serverless::Api",
                        "Properties": {"StageName": "Prod", "DefinitionUri": filename},
                    }
                }
            }

            provider = ApiProvider(make_mock_stacks_from_template(template))
            self.assertCountEqual(self.input_routes, provider.routes)

    @patch("samcli.lib.providers.cfn_base_api_provider.SwaggerReader")
    def test_with_swagger_as_both_body_and_uri_called(self, SwaggerReaderMock):
        body = {"some": "body"}
        filename = "somefile.txt"

        template = {
            "Resources": {
                "Api1": {
                    "Type": "AWS::Serverless::Api",
                    "Properties": {"StageName": "Prod", "DefinitionUri": filename, "DefinitionBody": body},
                }
            }
        }

        SwaggerReaderMock.return_value.read.return_value = make_swagger(self.input_routes)

        cwd = "foo"
        provider = ApiProvider(make_mock_stacks_from_template(template), cwd=cwd)
        self.assertCountEqual(self.input_routes, provider.routes)
        SwaggerReaderMock.assert_called_with(definition_body=body, definition_uri=filename, working_dir=cwd)

    def test_swagger_with_any_method(self):
        routes = [Route(path="/path", methods=["any"], function_name="SamFunc1")]

        expected_routes = [
            Route(
                path="/path",
                methods=["GET", "DELETE", "PUT", "POST", "HEAD", "OPTIONS", "PATCH"],
                function_name="SamFunc1",
            )
        ]

        template = {
            "Resources": {
                "Api1": {
                    "Type": "AWS::Serverless::Api",
                    "Properties": {"StageName": "Prod", "DefinitionBody": make_swagger(routes)},
                }
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))
        self.assertCountEqual(expected_routes, provider.routes)

    def test_with_binary_media_types(self):
        template = {
            "Resources": {
                "Api1": {
                    "Type": "AWS::Serverless::Api",
                    "Properties": {
                        "StageName": "Prod",
                        "DefinitionBody": make_swagger(self.input_routes, binary_media_types=self.binary_types),
                    },
                }
            }
        }

        expected_binary_types = sorted(self.binary_types)
        expected_routes = [
            Route(path="/path1", methods=["GET", "POST"], function_name="SamFunc1"),
            Route(path="/path2", methods=["GET", "PUT"], function_name="SamFunc1"),
            Route(path="/path3", methods=["DELETE"], function_name="SamFunc1"),
        ]

        provider = ApiProvider(make_mock_stacks_from_template(template))
        self.assertCountEqual(expected_routes, provider.routes)
        self.assertCountEqual(provider.api.binary_media_types, expected_binary_types)

    def test_with_binary_media_types_in_swagger_and_on_resource(self):
        input_routes = [Route(path="/path", methods=["OPTIONS"], function_name="SamFunc1")]
        extra_binary_types = ["text/html"]

        template = {
            "Resources": {
                "Api1": {
                    "Type": "AWS::Serverless::Api",
                    "Properties": {
                        "BinaryMediaTypes": extra_binary_types,
                        "StageName": "Prod",
                        "DefinitionBody": make_swagger(input_routes, binary_media_types=self.binary_types),
                    },
                }
            }
        }

        expected_binary_types = sorted(self.binary_types + extra_binary_types)
        expected_routes = [Route(path="/path", methods=["OPTIONS"], function_name="SamFunc1")]

        provider = ApiProvider(make_mock_stacks_from_template(template))
        self.assertCountEqual(expected_routes, provider.routes)
        self.assertCountEqual(provider.api.binary_media_types, expected_binary_types)


class TestSamApiProviderWithExplicitAndImplicitApis(TestCase):
    def setUp(self):
        self.stage_name = "Prod"
        self.explicit_routes = [
            Route(path="/path1", methods=["GET"], function_name="explicitfunction"),
            Route(path="/path2", methods=["GET"], function_name="explicitfunction"),
            Route(path="/path3", methods=["GET"], function_name="explicitfunction"),
        ]

        self.swagger = make_swagger(self.explicit_routes)

        self.template = {
            "Resources": {
                "Api1": {"Type": "AWS::Serverless::Api", "Properties": {"StageName": "Prod"}},
                "ImplicitFunc": {
                    "Type": "AWS::Serverless::Function",
                    "Properties": {"CodeUri": "/usr/foo/bar", "Runtime": "nodejs4.3", "Handler": "index.handler"},
                },
            }
        }

    def test_must_union_implicit_and_explicit(self):
        events = {
            "Event1": {"Type": "Api", "Properties": {"Path": "/path1", "Method": "POST"}},
            "Event2": {"Type": "Api", "Properties": {"Path": "/path2", "Method": "POST"}},
            "Event3": {"Type": "Api", "Properties": {"Path": "/path3", "Method": "POST"}},
        }

        self.template["Resources"]["Api1"]["Properties"]["DefinitionBody"] = self.swagger
        self.template["Resources"]["ImplicitFunc"]["Properties"]["Events"] = events

        expected_routes = [
            # From Explicit APIs
            Route(path="/path1", methods=["GET"], function_name="explicitfunction"),
            Route(path="/path2", methods=["GET"], function_name="explicitfunction"),
            Route(path="/path3", methods=["GET"], function_name="explicitfunction"),
            # From Implicit APIs
            Route(path="/path1", methods=["POST"], function_name="ImplicitFunc"),
            Route(path="/path2", methods=["POST"], function_name="ImplicitFunc"),
            Route(path="/path3", methods=["POST"], function_name="ImplicitFunc"),
        ]

        provider = ApiProvider(make_mock_stacks_from_template(self.template))
        self.assertCountEqual(expected_routes, provider.routes)

    def test_must_prefer_implicit_api_over_explicit(self):
        implicit_routes = {
            "Event1": {
                "Type": "Api",
                "Properties": {
                    # This API is duplicated between implicit & explicit
                    "Path": "/path1",
                    "Method": "get",
                },
            },
            "Event2": {"Type": "Api", "Properties": {"Path": "/path2", "Method": "POST"}},
        }

        self.template["Resources"]["Api1"]["Properties"]["DefinitionBody"] = self.swagger
        self.template["Resources"]["ImplicitFunc"]["Properties"]["Events"] = implicit_routes

        expected_routes = [
            Route(path="/path1", methods=["GET"], function_name="ImplicitFunc"),
            # Comes from Implicit
            Route(path="/path2", methods=["GET"], function_name="explicitfunction"),
            Route(path="/path2", methods=["POST"], function_name="ImplicitFunc"),
            # Comes from implicit
            Route(path="/path3", methods=["GET"], function_name="explicitfunction"),
        ]

        provider = ApiProvider(make_mock_stacks_from_template(self.template))
        self.assertCountEqual(expected_routes, provider.routes)

    def test_must_prefer_implicit_with_any_method(self):
        implicit_routes = {
            "Event1": {
                "Type": "Api",
                "Properties": {
                    # This API is duplicated between implicit & explicit
                    "Path": "/path",
                    "Method": "ANY",
                },
            }
        }

        explicit_routes = [
            # Explicit should be over masked completely by implicit, because of "ANY"
            Route(path="/path", methods=["GET"], function_name="explicitfunction"),
            Route(path="/path", methods=["DELETE"], function_name="explicitfunction"),
        ]

        self.template["Resources"]["Api1"]["Properties"]["DefinitionBody"] = make_swagger(explicit_routes)
        self.template["Resources"]["ImplicitFunc"]["Properties"]["Events"] = implicit_routes

        expected_routes = [
            Route(
                path="/path",
                methods=["GET", "DELETE", "PUT", "POST", "HEAD", "OPTIONS", "PATCH"],
                function_name="ImplicitFunc",
            )
        ]

        provider = ApiProvider(make_mock_stacks_from_template(self.template))
        self.assertCountEqual(expected_routes, provider.routes)

    def test_with_any_method_on_both(self):
        implicit_routes = {
            "Event1": {
                "Type": "Api",
                "Properties": {
                    # This API is duplicated between implicit & explicit
                    "Path": "/path",
                    "Method": "ANY",
                },
            },
            "Event2": {
                "Type": "Api",
                "Properties": {
                    # This API is duplicated between implicit & explicit
                    "Path": "/path2",
                    "Method": "GET",
                },
            },
        }

        explicit_routes = [
            # Explicit should be over masked completely by implicit, because of "ANY"
            Route(path="/path", methods=["ANY"], function_name="explicitfunction"),
            Route(path="/path2", methods=["POST"], function_name="explicitfunction"),
        ]

        self.template["Resources"]["Api1"]["Properties"]["DefinitionBody"] = make_swagger(explicit_routes)
        self.template["Resources"]["ImplicitFunc"]["Properties"]["Events"] = implicit_routes

        expected_routes = [
            Route(
                path="/path",
                methods=["GET", "DELETE", "PUT", "POST", "HEAD", "OPTIONS", "PATCH"],
                function_name="ImplicitFunc",
            ),
            Route(path="/path2", methods=["GET"], function_name="ImplicitFunc"),
            Route(path="/path2", methods=["POST"], function_name="explicitfunction"),
        ]

        provider = ApiProvider(make_mock_stacks_from_template(self.template))
        self.assertCountEqual(expected_routes, provider.routes)

    def test_must_add_explicit_api_when_ref_with_rest_api_id(self):
        events = {
            "Event1": {
                "Type": "Api",
                "Properties": {
                    "Path": "/newpath1",
                    "Method": "POST",
                    "RestApiId": "Api1",  # This path must get added to this API
                },
            },
            "Event2": {
                "Type": "Api",
                "Properties": {
                    "Path": "/newpath2",
                    "Method": "POST",
                    "RestApiId": {"Ref": "Api1"},  # This path must get added to this API
                },
            },
        }

        self.template["Resources"]["Api1"]["Properties"]["DefinitionBody"] = self.swagger
        self.template["Resources"]["ImplicitFunc"]["Properties"]["Events"] = events

        expected_routes = [
            # From Explicit APIs
            Route(path="/path1", methods=["GET"], function_name="explicitfunction"),
            Route(path="/path2", methods=["GET"], function_name="explicitfunction"),
            Route(path="/path3", methods=["GET"], function_name="explicitfunction"),
            # From Implicit APIs
            Route(path="/newpath1", methods=["POST"], function_name="ImplicitFunc"),
            Route(path="/newpath2", methods=["POST"], function_name="ImplicitFunc"),
        ]

        provider = ApiProvider(make_mock_stacks_from_template(self.template))
        self.assertCountEqual(expected_routes, provider.routes)

    def test_both_routes_must_get_binary_media_types(self):
        events = {
            "Event1": {"Type": "Api", "Properties": {"Path": "/newpath1", "Method": "POST"}},
            "Event2": {"Type": "Api", "Properties": {"Path": "/newpath2", "Method": "POST"}},
        }

        # Binary type for implicit
        self.template["Globals"] = {"Api": {"BinaryMediaTypes": ["image~1gif", "image~1png"]}}
        self.template["Resources"]["ImplicitFunc"]["Properties"]["Events"] = events

        self.template["Resources"]["Api1"]["Properties"]["DefinitionBody"] = self.swagger
        # Binary type for explicit
        self.template["Resources"]["Api1"]["Properties"]["BinaryMediaTypes"] = ["explicit/type1", "explicit/type2"]

        # Because of Globals, binary types will be concatenated on the explicit API
        expected_explicit_binary_types = ["explicit/type1", "explicit/type2", "image/gif", "image/png"]

        expected_routes = [
            # From Explicit APIs
            Route(path="/path1", methods=["GET"], function_name="explicitfunction"),
            Route(path="/path2", methods=["GET"], function_name="explicitfunction"),
            Route(path="/path3", methods=["GET"], function_name="explicitfunction"),
            # From Implicit APIs
            Route(path="/newpath1", methods=["POST"], function_name="ImplicitFunc"),
            Route(path="/newpath2", methods=["POST"], function_name="ImplicitFunc"),
        ]

        provider = ApiProvider(make_mock_stacks_from_template(self.template))
        self.assertCountEqual(expected_routes, provider.routes)
        self.assertCountEqual(provider.api.binary_media_types, expected_explicit_binary_types)

    def test_binary_media_types_with_rest_api_id_reference(self):
        events = {
            "Event1": {
                "Type": "Api",
                "Properties": {"Path": "/connected-to-explicit-path", "Method": "POST", "RestApiId": "Api1"},
            },
            "Event2": {"Type": "Api", "Properties": {"Path": "/true-implicit-path", "Method": "POST"}},
        }

        # Binary type for implicit
        self.template["Globals"] = {"Api": {"BinaryMediaTypes": ["image~1gif", "image~1png"]}}
        self.template["Resources"]["ImplicitFunc"]["Properties"]["Events"] = events

        self.template["Resources"]["Api1"]["Properties"]["DefinitionBody"] = self.swagger
        # Binary type for explicit
        self.template["Resources"]["Api1"]["Properties"]["BinaryMediaTypes"] = ["explicit/type1", "explicit/type2"]

        # Because of Globals, binary types will be concatenated on the explicit API
        expected_explicit_binary_types = ["explicit/type1", "explicit/type2", "image/gif", "image/png"]
        # expected_implicit_binary_types = ["image/gif", "image/png"]

        expected_routes = [
            # From Explicit APIs
            Route(path="/path1", methods=["GET"], function_name="explicitfunction"),
            Route(path="/path2", methods=["GET"], function_name="explicitfunction"),
            Route(path="/path3", methods=["GET"], function_name="explicitfunction"),
            # Because of the RestApiId, Implicit APIs will also get the binary media types inherited from
            # the corresponding Explicit API
            Route(path="/connected-to-explicit-path", methods=["POST"], function_name="ImplicitFunc"),
            # This is still just a true implicit API because it does not have RestApiId property
            Route(path="/true-implicit-path", methods=["POST"], function_name="ImplicitFunc"),
        ]

        provider = ApiProvider(make_mock_stacks_from_template(self.template))
        self.assertCountEqual(expected_routes, provider.routes)
        self.assertCountEqual(provider.api.binary_media_types, expected_explicit_binary_types)


class TestSamStageValues(TestCase):
    def test_provider_parse_stage_name(self):
        template = {
            "Resources": {
                "TestApi": {
                    "Type": "AWS::Serverless::Api",
                    "Properties": {
                        "StageName": "dev",
                        "DefinitionBody": {
                            "swagger": "2.0",
                            "paths": {
                                "/path": {
                                    "get": {
                                        "x-amazon-apigateway-integration": {
                                            "httpMethod": "POST",
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                }
                            },
                        },
                    },
                }
            }
        }
        provider = ApiProvider(make_mock_stacks_from_template(template))
        route1 = Route(path="/path", methods=["GET"], function_name="NoApiEventFunction")

        self.assertIn(route1, provider.routes)
        self.assertEqual(provider.api.stage_name, "dev")
        self.assertEqual(provider.api.stage_variables, None)

    def test_provider_stage_variables(self):
        template = {
            "Resources": {
                "TestApi": {
                    "Type": "AWS::Serverless::Api",
                    "Properties": {
                        "StageName": "dev",
                        "Variables": {"vis": "data", "random": "test", "foo": "bar"},
                        "DefinitionBody": {
                            "swagger": "2.0",
                            "paths": {
                                "/path": {
                                    "get": {
                                        "x-amazon-apigateway-integration": {
                                            "httpMethod": "POST",
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                }
                            },
                        },
                    },
                }
            }
        }
        provider = ApiProvider(make_mock_stacks_from_template(template))
        route1 = Route(path="/path", methods=["GET"], function_name="NoApiEventFunction")

        self.assertIn(route1, provider.routes)
        self.assertEqual(provider.api.stage_name, "dev")
        self.assertEqual(provider.api.stage_variables, {"vis": "data", "random": "test", "foo": "bar"})

    def test_multi_stage_get_all(self):
        template = OrderedDict({"Resources": {}})
        template["Resources"]["TestApi"] = {
            "Type": "AWS::Serverless::Api",
            "Properties": {
                "StageName": "dev",
                "Variables": {"vis": "data", "random": "test", "foo": "bar"},
                "DefinitionBody": {
                    "swagger": "2.0",
                    "paths": {
                        "/path2": {
                            "get": {
                                "x-amazon-apigateway-integration": {
                                    "httpMethod": "POST",
                                    "type": "aws_proxy",
                                    "uri": {
                                        "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                        "/functions/${NoApiEventFunction.Arn}/invocations"
                                    },
                                    "responses": {},
                                }
                            }
                        }
                    },
                },
            },
        }

        template["Resources"]["ProductionApi"] = {
            "Type": "AWS::Serverless::Api",
            "Properties": {
                "StageName": "Production",
                "Variables": {"vis": "prod data", "random": "test", "foo": "bar"},
                "DefinitionBody": {
                    "swagger": "2.0",
                    "paths": {
                        "/path": {
                            "get": {
                                "x-amazon-apigateway-integration": {
                                    "httpMethod": "POST",
                                    "type": "aws_proxy",
                                    "uri": {
                                        "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                        "/functions/${NoApiEventFunction.Arn}/invocations"
                                    },
                                    "responses": {},
                                }
                            }
                        },
                        "/anotherpath": {
                            "post": {
                                "x-amazon-apigateway-integration": {
                                    "httpMethod": "POST",
                                    "type": "aws_proxy",
                                    "uri": {
                                        "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                        "/functions/${NoApiEventFunction.Arn}/invocations"
                                    },
                                    "responses": {},
                                }
                            }
                        },
                    },
                },
            },
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        result = [f for f in provider.get_all()]
        routes = result[0].routes

        route1 = Route(path="/path2", methods=["GET"], function_name="NoApiEventFunction")
        route2 = Route(path="/path", methods=["GET"], function_name="NoApiEventFunction")
        route3 = Route(path="/anotherpath", methods=["POST"], function_name="NoApiEventFunction")
        self.assertEqual(len(routes), 3)
        self.assertIn(route1, routes)
        self.assertIn(route2, routes)
        self.assertIn(route3, routes)

        self.assertEqual(provider.api.stage_name, "Production")
        self.assertEqual(provider.api.stage_variables, {"vis": "prod data", "random": "test", "foo": "bar"})


class TestSamCors(TestCase):
    def test_provider_parse_cors_with_unresolved_intrinsic(self):
        template = {
            "Resources": {
                "TestApi": {
                    "Type": "AWS::Serverless::Api",
                    "Properties": {
                        "StageName": "Prod",
                        "Cors": {"AllowOrigin": {"Fn:Sub": "Some string to sub"}},
                        "DefinitionBody": {
                            "swagger": "2.0",
                            "paths": {
                                "/path2": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                                "/path": {
                                    "get": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                            },
                        },
                    },
                }
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        routes = provider.routes
        cors = Cors(
            allow_origin=None,
            allow_methods=",".join(sorted(["GET", "DELETE", "PUT", "POST", "HEAD", "OPTIONS", "PATCH"])),
        )
        route1 = Route(path="/path2", methods=["POST", "OPTIONS"], function_name="NoApiEventFunction")
        route2 = Route(path="/path", methods=["GET", "OPTIONS"], function_name="NoApiEventFunction")

        self.assertEqual(len(routes), 2)
        self.assertIn(route1, routes)
        self.assertIn(route2, routes)
        self.assertEqual(provider.api.cors, cors)

    def test_provider_parse_cors_string(self):
        template = {
            "Resources": {
                "TestApi": {
                    "Type": "AWS::Serverless::Api",
                    "Properties": {
                        "StageName": "Prod",
                        "Cors": "'*'",
                        "DefinitionBody": {
                            "swagger": "2.0",
                            "paths": {
                                "/path2": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                                "/path": {
                                    "get": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                            },
                        },
                    },
                }
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        routes = provider.routes
        cors = Cors(
            allow_origin="*",
            allow_methods=",".join(sorted(["GET", "DELETE", "PUT", "POST", "HEAD", "OPTIONS", "PATCH"])),
        )
        route1 = Route(path="/path2", methods=["POST", "OPTIONS"], function_name="NoApiEventFunction")
        route2 = Route(path="/path", methods=["GET", "OPTIONS"], function_name="NoApiEventFunction")

        self.assertEqual(len(routes), 2)
        self.assertIn(route1, routes)
        self.assertIn(route2, routes)
        self.assertEqual(provider.api.cors, cors)

    def test_provider_parse_cors_dict(self):
        template = {
            "Resources": {
                "TestApi": {
                    "Type": "AWS::Serverless::Api",
                    "Properties": {
                        "StageName": "Prod",
                        "Cors": {
                            "AllowMethods": "'POST, GET'",
                            "AllowOrigin": "'*'",
                            "AllowHeaders": "'Upgrade-Insecure-Requests'",
                            "MaxAge": "'600'",
                        },
                        "DefinitionBody": {
                            "swagger": "2.0",
                            "paths": {
                                "/path2": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                                "/path": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                            },
                        },
                    },
                }
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        routes = provider.routes
        cors = Cors(
            allow_origin="*",
            allow_methods=",".join(sorted(["POST", "GET", "OPTIONS"])),
            allow_headers="Upgrade-Insecure-Requests",
            max_age="600",
        )
        route1 = Route(path="/path2", methods=["POST", "OPTIONS"], function_name="NoApiEventFunction")
        route2 = Route(path="/path", methods=["POST", "OPTIONS"], function_name="NoApiEventFunction")

        self.assertEqual(len(routes), 2)
        self.assertIn(route1, routes)
        self.assertIn(route2, routes)
        self.assertEqual(provider.api.cors, cors)

    def test_provider_parse_cors_dict_star_allow(self):
        template = {
            "Resources": {
                "TestApi": {
                    "Type": "AWS::Serverless::Api",
                    "Properties": {
                        "StageName": "Prod",
                        "Cors": {
                            "AllowMethods": "'*'",
                            "AllowOrigin": "'*'",
                            "AllowHeaders": "'Upgrade-Insecure-Requests'",
                            "MaxAge": "'600'",
                        },
                        "DefinitionBody": {
                            "swagger": "2.0",
                            "paths": {
                                "/path2": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                                "/path": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                            },
                        },
                    },
                }
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        routes = provider.routes
        cors = Cors(
            allow_origin="*",
            allow_methods=",".join(sorted(Route.ANY_HTTP_METHODS)),
            allow_headers="Upgrade-Insecure-Requests",
            max_age="600",
        )
        route1 = Route(path="/path2", methods=["POST", "OPTIONS"], function_name="NoApiEventFunction")
        route2 = Route(path="/path", methods=["POST", "OPTIONS"], function_name="NoApiEventFunction")

        self.assertEqual(len(routes), 2)
        self.assertIn(route1, routes)
        self.assertIn(route2, routes)
        self.assertEqual(provider.api.cors, cors)

    def test_raises_error_when_cors_allowmethods_not_single_quoted(self):
        template = {
            "Resources": {
                "TestApi": {
                    "Type": "AWS::Serverless::Api",
                    "Properties": {
                        "StageName": "Prod",
                        "Cors": {
                            "AllowMethods": "GET, INVALID_METHOD",
                            "AllowOrigin": "'*'",
                            "AllowHeaders": "'Upgrade-Insecure-Requests'",
                            "MaxAge": "'600'",
                        },
                        "DefinitionBody": {
                            "paths": {
                                "/path2": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                                "/path": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                            }
                        },
                    },
                }
            }
        }
        with self.assertRaises(
            InvalidSamDocumentException, msg="ApiProvider should fail for Invalid Cors AllowMethods not single quoted"
        ):
            ApiProvider(make_mock_stacks_from_template(template))

    def test_raises_error_when_cors_value_not_single_quoted(self):
        template = {
            "Resources": {
                "TestApi": {
                    "Type": "AWS::Serverless::Api",
                    "Properties": {
                        "StageName": "Prod",
                        "Cors": "example.com",
                        "DefinitionBody": {
                            "paths": {
                                "/path2": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                                "/path": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                            }
                        },
                    },
                }
            }
        }
        with self.assertRaises(
            InvalidSamDocumentException, msg="ApiProvider should fail for Invalid Cors value not single quoted"
        ):
            ApiProvider(make_mock_stacks_from_template(template))

    def test_invalid_cors_dict_allow_methods(self):
        template = {
            "Resources": {
                "TestApi": {
                    "Type": "AWS::Serverless::Api",
                    "Properties": {
                        "StageName": "Prod",
                        "Cors": {
                            "AllowMethods": "'GET, INVALID_METHOD'",
                            "AllowOrigin": "'*'",
                            "AllowHeaders": "'Upgrade-Insecure-Requests'",
                            "MaxAge": "'600'",
                        },
                        "DefinitionBody": {
                            "paths": {
                                "/path2": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                                "/path": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                            }
                        },
                    },
                }
            }
        }
        with self.assertRaises(
            InvalidSamDocumentException, msg="ApiProvider should fail for Invalid Cors Allow method"
        ):
            ApiProvider(make_mock_stacks_from_template(template))

    def test_default_cors_dict_prop(self):
        template = {
            "Resources": {
                "TestApi": {
                    "Type": "AWS::Serverless::Api",
                    "Properties": {
                        "StageName": "Prod",
                        "Cors": {"AllowOrigin": "'www.domain.com'"},
                        "DefinitionBody": {
                            "swagger": "2.0",
                            "paths": {
                                "/path2": {
                                    "get": {
                                        "x-amazon-apigateway-integration": {
                                            "httpMethod": "POST",
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                }
                            },
                        },
                    },
                }
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        routes = provider.routes
        cors = Cors(allow_origin="www.domain.com", allow_methods=",".join(sorted(Route.ANY_HTTP_METHODS)))
        route1 = Route(path="/path2", methods=["GET", "OPTIONS"], function_name="NoApiEventFunction")
        self.assertEqual(len(routes), 1)
        self.assertIn(route1, routes)
        self.assertEqual(provider.api.cors, cors)

    def test_global_cors(self):
        template = {
            "Globals": {
                "Api": {
                    "Cors": {
                        "AllowMethods": "'GET'",
                        "AllowOrigin": "'*'",
                        "AllowHeaders": "'Upgrade-Insecure-Requests'",
                        "MaxAge": "'600'",
                    }
                }
            },
            "Resources": {
                "TestApi": {
                    "Type": "AWS::Serverless::Api",
                    "Properties": {
                        "StageName": "Prod",
                        "DefinitionBody": {
                            "swagger": "2.0",
                            "paths": {
                                "/path2": {
                                    "get": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                                "/path": {
                                    "get": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                            },
                        },
                    },
                }
            },
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        routes = provider.routes
        cors = Cors(
            allow_origin="*",
            allow_headers="Upgrade-Insecure-Requests",
            allow_methods=",".join(["GET", "OPTIONS"]),
            max_age="600",
        )
        route1 = Route(path="/path2", methods=["GET", "OPTIONS"], function_name="NoApiEventFunction")
        route2 = Route(path="/path", methods=["GET", "OPTIONS"], function_name="NoApiEventFunction")

        self.assertEqual(len(routes), 2)
        self.assertIn(route1, routes)
        self.assertIn(route2, routes)
        self.assertEqual(provider.api.cors, cors)


class TestSamHttpApiCors(TestCase):
    def test_provider_parse_cors_with_unresolved_intrinsic(self):
        template = {
            "Resources": {
                "TestApi": {
                    "Type": "AWS::Serverless::HttpApi",
                    "Properties": {
                        "StageName": "Prod",
                        "CorsConfiguration": {"AllowOrigins": {"Fn:Sub": "Some string to sub"}},
                        "DefinitionBody": {
                            "openapi": "3.0",
                            "paths": {
                                "/path2": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                                "/path": {
                                    "get": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                            },
                        },
                    },
                }
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        routes = provider.routes
        cors = Cors(
            allow_origin=None,
            allow_methods=",".join(sorted(["GET", "DELETE", "PUT", "POST", "HEAD", "OPTIONS", "PATCH"])),
        )
        route1 = Route(path="/path2", methods=["POST", "OPTIONS"], function_name="NoApiEventFunction")
        route2 = Route(path="/path", methods=["GET", "OPTIONS"], function_name="NoApiEventFunction")

        self.assertEqual(len(routes), 2)
        self.assertIn(route1, routes)
        self.assertIn(route2, routes)
        self.assertEqual(provider.api.cors, cors)

    def test_provider_parse_cors_true(self):
        template = {
            "Resources": {
                "TestApi": {
                    "Type": "AWS::Serverless::HttpApi",
                    "Properties": {
                        "StageName": "Prod",
                        "CorsConfiguration": True,
                        "DefinitionBody": {
                            "openapi": "3.0",
                            "paths": {
                                "/path2": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                                "/path": {
                                    "get": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                            },
                        },
                    },
                }
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        routes = provider.routes
        cors = Cors(
            allow_origin="*",
            allow_methods=",".join(sorted(["GET", "DELETE", "PUT", "POST", "HEAD", "OPTIONS", "PATCH"])),
        )
        route1 = Route(path="/path2", methods=["POST", "OPTIONS"], function_name="NoApiEventFunction")
        route2 = Route(path="/path", methods=["GET", "OPTIONS"], function_name="NoApiEventFunction")

        self.assertEqual(len(routes), 2)
        self.assertIn(route1, routes)
        self.assertIn(route2, routes)
        self.assertEqual(provider.api.cors, cors)

    def test_provider_parse_cors_false(self):
        template = {
            "Resources": {
                "TestApi": {
                    "Type": "AWS::Serverless::HttpApi",
                    "Properties": {
                        "StageName": "Prod",
                        "CorsConfiguration": False,
                        "DefinitionBody": {
                            "openapi": "3.0",
                            "paths": {
                                "/path2": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                                "/path": {
                                    "get": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                            },
                        },
                    },
                }
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        routes = provider.routes
        cors = None
        route1 = Route(path="/path2", methods=["POST"], function_name="NoApiEventFunction")
        route2 = Route(path="/path", methods=["GET"], function_name="NoApiEventFunction")

        self.assertEqual(len(routes), 2)
        self.assertIn(route1, routes)
        self.assertIn(route2, routes)
        self.assertEqual(provider.api.cors, cors)

    def test_provider_parse_cors_dict(self):
        template = {
            "Resources": {
                "TestApi": {
                    "Type": "AWS::Serverless::HttpApi",
                    "Properties": {
                        "StageName": "Prod",
                        "CorsConfiguration": {
                            "AllowMethods": ["POST", "GET"],
                            "AllowOrigins": ["*"],
                            "AllowHeaders": ["Upgrade-Insecure-Requests"],
                            "MaxAge": 600,
                        },
                        "DefinitionBody": {
                            "openapi": "3.0",
                            "paths": {
                                "/path2": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                                "/path": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                            },
                        },
                    },
                }
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        routes = provider.routes
        cors = Cors(
            allow_origin="*",
            allow_methods=",".join(sorted(["POST", "GET", "OPTIONS"])),
            allow_headers="Upgrade-Insecure-Requests",
            max_age=600,
        )
        route1 = Route(path="/path2", methods=["POST", "OPTIONS"], function_name="NoApiEventFunction")
        route2 = Route(path="/path", methods=["POST", "OPTIONS"], function_name="NoApiEventFunction")

        self.assertEqual(len(routes), 2)
        self.assertIn(route1, routes)
        self.assertIn(route2, routes)
        self.assertEqual(provider.api.cors, cors)

    def test_provider_parse_cors_dict_star_allow(self):
        template = {
            "Resources": {
                "TestApi": {
                    "Type": "AWS::Serverless::HttpApi",
                    "Properties": {
                        "StageName": "Prod",
                        "CorsConfiguration": {
                            "AllowMethods": ["*"],
                            "AllowOrigins": ["*"],
                            "AllowHeaders": ["Upgrade-Insecure-Requests"],
                            "MaxAge": 600,
                        },
                        "DefinitionBody": {
                            "openapi": "3.0",
                            "paths": {
                                "/path2": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                                "/path": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                            },
                        },
                    },
                }
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        routes = provider.routes
        cors = Cors(
            allow_origin="*",
            allow_methods=",".join(sorted(Route.ANY_HTTP_METHODS)),
            allow_headers="Upgrade-Insecure-Requests",
            max_age=600,
        )
        route1 = Route(path="/path2", methods=["POST", "OPTIONS"], function_name="NoApiEventFunction")
        route2 = Route(path="/path", methods=["POST", "OPTIONS"], function_name="NoApiEventFunction")

        self.assertEqual(len(routes), 2)
        self.assertIn(route1, routes)
        self.assertIn(route2, routes)
        self.assertEqual(provider.api.cors, cors)

    def test_invalid_cors_dict_allow_methods(self):
        template = {
            "Resources": {
                "TestApi": {
                    "Type": "AWS::Serverless::HttpApi",
                    "Properties": {
                        "StageName": "Prod",
                        "CorsConfiguration": {
                            "AllowMethods": ["GET", "INVALID_METHOD"],
                            "AllowOrigins": ["*"],
                            "AllowHeaders": ["Upgrade-Insecure-Requests"],
                            "MaxAge": 600,
                        },
                        "DefinitionBody": {
                            "paths": {
                                "/path2": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                                "/path": {
                                    "post": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                            }
                        },
                    },
                }
            }
        }
        with self.assertRaises(
            InvalidSamDocumentException, msg="ApiProvider should fail for Invalid Cors Allow method"
        ):
            ApiProvider(make_mock_stacks_from_template(template))

    def test_default_cors_dict_prop(self):
        template = {
            "Resources": {
                "TestApi": {
                    "Type": "AWS::Serverless::HttpApi",
                    "Properties": {
                        "StageName": "Prod",
                        "CorsConfiguration": {"AllowOrigins": ["www.domain.com"]},
                        "DefinitionBody": {
                            "openapi": "3.0",
                            "paths": {
                                "/path2": {
                                    "get": {
                                        "x-amazon-apigateway-integration": {
                                            "httpMethod": "POST",
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                }
                            },
                        },
                    },
                }
            }
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        routes = provider.routes
        cors = Cors(allow_origin="www.domain.com", allow_methods=",".join(sorted(Route.ANY_HTTP_METHODS)))
        route1 = Route(path="/path2", methods=["GET", "OPTIONS"], function_name="NoApiEventFunction")
        self.assertEqual(len(routes), 1)
        self.assertIn(route1, routes)
        self.assertEqual(provider.api.cors, cors)

    def test_global_cors(self):
        template = {
            "Globals": {
                "HttpApi": {
                    "CorsConfiguration": {
                        "AllowMethods": ["GET"],
                        "AllowOrigins": ["*"],
                        "AllowHeaders": ["Upgrade-Insecure-Requests"],
                        "MaxAge": 600,
                    }
                }
            },
            "Resources": {
                "TestApi": {
                    "Type": "AWS::Serverless::HttpApi",
                    "Properties": {
                        "StageName": "Prod",
                        "DefinitionBody": {
                            "openapi": "3.0",
                            "paths": {
                                "/path2": {
                                    "get": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                                "/path": {
                                    "get": {
                                        "x-amazon-apigateway-integration": {
                                            "type": "aws_proxy",
                                            "uri": {
                                                "Fn::Sub": "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31"
                                                "/functions/${NoApiEventFunction.Arn}/invocations"
                                            },
                                            "responses": {},
                                        }
                                    }
                                },
                            },
                        },
                    },
                }
            },
        }

        provider = ApiProvider(make_mock_stacks_from_template(template))

        routes = provider.routes
        cors = Cors(
            allow_origin="*",
            allow_headers="Upgrade-Insecure-Requests",
            allow_methods=",".join(["GET", "OPTIONS"]),
            max_age=600,
        )
        route1 = Route(path="/path2", methods=["GET", "OPTIONS"], function_name="NoApiEventFunction")
        route2 = Route(path="/path", methods=["GET", "OPTIONS"], function_name="NoApiEventFunction")

        self.assertEqual(len(routes), 2)
        self.assertIn(route1, routes)
        self.assertIn(route2, routes)
        self.assertEqual(provider.api.cors, cors)


class TestSamApiUsingAuthorizers(TestCase):
    @parameterized.expand(
        [(SamApiProvider()._extract_from_serverless_api,), (SamApiProvider()._extract_from_serverless_http,)]
    )
    @patch("samcli.lib.providers.cfn_base_api_provider.CfnBaseApiProvider.extract_swagger_route")
    @patch("samcli.lib.providers.sam_api_provider.SamApiProvider._extract_authorizers_from_props")
    def test_extract_serverless_api_extracts_default_authorizer(
        self, extraction_method, extract_authorizers_mock, extract_swagger_route_mock
    ):
        authorizer_name = "myauth"

        properties = {
            "Properties": {"DefinitionBody": {"something": "here"}, "Auth": {"DefaultAuthorizer": authorizer_name}}
        }

        logical_id_mock = Mock()
        api_collector_mock = Mock()
        api_collector_mock.set_default_authorizer = Mock()

        extraction_method(Mock(), logical_id_mock, properties, api_collector_mock, Mock())

        api_collector_mock.set_default_authorizer.assert_called_with(logical_id_mock, authorizer_name)

    @parameterized.expand(
        [("when enabled ignores ignores authorizers", True), ("when disabled extracts authorizers as normal", False)]
    )
    @patch("samcli.lib.providers.sam_api_provider.SamApiProvider._extract_authorizers_from_props")
    @patch("samcli.lib.providers.sam_api_provider.CfnBaseApiProvider.extract_swagger_route")
    @patch("samcli.lib.providers.sam_api_provider.LOG.debug")
    def test_extract_from_serverless_http_with_disable_authorizer_flag(
        self,
        _,
        disable_authorizer,
        mock_debug_log: Mock,
        mock_extract_swagger_route: Mock,
        mock_extract_authorizers_from_props: Mock,
    ):
        provider = SamApiProvider()
        template = {
            "Properties": {
                "DefinitionBody": "mock-body",
                "DefinitionUri": "mock-uri",
                "StageName": "stage-name",
                "StageVariables": {},
                "Auth": {"DefaultAuthorizer": "Authorizer"},
            }
        }
        mock_collector = Mock()
        provider._extract_from_serverless_http(
            stack_path="/",
            logical_id="id",
            api_resource=template,
            collector=mock_collector,
            disable_authorizer=disable_authorizer,
        )

        if disable_authorizer:
            mock_collector.set_default_authorizer.assert_not_called()
            mock_extract_authorizers_from_props.assert_not_called()

        if not disable_authorizer:
            mock_collector.set_default_authorizer.assert_called()
            mock_extract_authorizers_from_props.assert_called()

    @parameterized.expand(
        [("when enabled ignores authorizers", True), ("when disabled extracts authorizers as normal", False)]
    )
    @patch("samcli.lib.providers.sam_api_provider.SamApiProvider._extract_authorizers_from_props")
    @patch("samcli.lib.providers.sam_api_provider.CfnBaseApiProvider.extract_swagger_route")
    @patch("samcli.lib.providers.sam_api_provider.LOG.debug")
    def test_extract_from_serverless_api_with_disable_authorizer_flag(
        self,
        _,
        disable_authorizer,
        mock_debug_log: Mock,
        mock_extract_swagger_route: Mock,
        mock_extract_authorizers_from_props: Mock,
    ):
        provider = SamApiProvider()
        template = {
            "Properties": {
                "DefinitionBody": "mock-body",
                "DefinitionUri": "mock-uri",
                "StageName": "stage-name",
                "StageVariables": {},
                "Auth": {"DefaultAuthorizer": "MyAuthorizer"},
            }
        }
        mock_collector = Mock()
        provider._extract_from_serverless_api(
            stack_path="/",
            logical_id="id",
            api_resource=template,
            collector=mock_collector,
            disable_authorizer=disable_authorizer,
        )

        if disable_authorizer:
            mock_debug_log.assert_called_with("Authorizer not found or disabled, returning early")
            mock_collector.set_default_authorizer.assert_not_called()
            mock_extract_authorizers_from_props.assert_not_called()

        if not disable_authorizer:
            mock_debug_log.assert_not_called()
            mock_collector.set_default_authorizer.assert_called()
            mock_extract_authorizers_from_props.assert_called()

    @parameterized.expand(
        [("sets authorizer name to None", True, None), ("sets authorizer name to Authorizer", False, "Authorizer")]
    )
    def test_convert_event_route_with_disable_authorizer_flag(self, _, disable_authorizer, expected):
        event_properties = {
            "Path": "MockPath",
            "Method": "MockMethod",
            "RestApiId": "MockId",
            "Auth": {"Authorizer": "Authorizer"},
        }
        _, route = SamApiProvider._convert_event_route(
            stack_path="",
            lambda_logical_id="MyLambda",
            event_properties=event_properties,
            event_type="Api",
            disable_authorizer=disable_authorizer,
        )
        self.assertEqual(route.authorizer_name, expected)

    @parameterized.expand(
        [
            (  # test token + swagger 2.0
                {
                    "Authorizers": {
                        "mycoolauthorizer": {
                            "FunctionPayloadType": "TOKEN",
                            "Identity": {
                                "Header": "myheader",
                            },
                            "FunctionArn": "will_be_mocked",
                        }
                    }
                },
                {
                    "mycoolauthorizer": LambdaAuthorizer(
                        payload_version="1.0",
                        authorizer_name="mycoolauthorizer",
                        type="token",
                        lambda_name=ANY,
                        identity_sources=["method.request.header.myheader"],
                    )
                },
                Route.API,
            ),
            (  # test no identity header + token + swagger 2.0
                {
                    "Authorizers": {
                        "mycoolauthorizer": {
                            "FunctionPayloadType": "TOKEN",
                            "FunctionArn": "will_be_mocked",
                        }
                    }
                },
                {
                    "mycoolauthorizer": LambdaAuthorizer(
                        payload_version="1.0",
                        authorizer_name="mycoolauthorizer",
                        type="token",
                        lambda_name=ANY,
                        identity_sources=["method.request.header.Authorization"],
                    )
                },
                Route.API,
            ),
            (  # test request + swagger 2.0
                {
                    "Authorizers": {
                        "mycoolauthorizer": {
                            "FunctionPayloadType": "REQUEST",
                            "Identity": {
                                "QueryStrings": ["query1", "query2"],
                                "Headers": ["header1", "header2"],
                                "Context": ["context1", "context2"],
                                "StageVariables": ["stage1", "stage2"],
                            },
                            "FunctionArn": "will_be_mocked",
                            "AuthorizerPayloadFormatVersion": "1.0",
                        }
                    }
                },
                {
                    "mycoolauthorizer": LambdaAuthorizer(
                        payload_version="1.0",
                        authorizer_name="mycoolauthorizer",
                        type="request",
                        lambda_name=ANY,
                        identity_sources=[
                            "method.request.header.header1",
                            "method.request.header.header2",
                            "method.request.querystring.query1",
                            "method.request.querystring.query2",
                            "context.context1",
                            "context.context2",
                            "stageVariables.stage1",
                            "stageVariables.stage2",
                        ],
                    )
                },
                Route.API,
            ),
            (  # test openapi3 (http api event)
                {
                    "Authorizers": {
                        "mycoolauthorizer": {
                            "Identity": {
                                "QueryStrings": ["query1", "query2"],
                                "Headers": ["header1", "header2"],
                                "Context": ["context1", "context2"],
                                "StageVariables": ["stage1", "stage2"],
                            },
                            "AuthorizerPayloadFormatVersion": "2.0",
                            "EnableSimpleResponses": True,
                            "FunctionArn": "will_be_mocked",
                        }
                    }
                },
                {
                    "mycoolauthorizer": LambdaAuthorizer(
                        payload_version="2.0",
                        authorizer_name="mycoolauthorizer",
                        type="request",
                        lambda_name=ANY,
                        use_simple_response=True,
                        identity_sources=[
                            "$request.header.header1",
                            "$request.header.header2",
                            "$request.querystring.query1",
                            "$request.querystring.query2",
                            "$context.context1",
                            "$context.context2",
                            "$stageVariables.stage1",
                            "$stageVariables.stage2",
                        ],
                    )
                },
                Route.HTTP,
            ),
        ]
    )
    @patch("samcli.commands.local.lib.swagger.integration_uri.LambdaUri.get_function_name")
    def test_extract_lambda_authorizers_from_properties(
        self, properties, expected_authorizers, event_type, function_name_mock
    ):
        logical_id = "mycoolauthorizer"

        function_name_mock.return_value = logical_id

        collector_mock = Mock()
        collector_mock.add_authorizers = Mock()

        SamApiProvider._extract_authorizers_from_props(logical_id, properties, collector_mock, event_type)

        collector_mock.add_authorizers.assert_called_with(logical_id, expected_authorizers)

    @parameterized.expand(
        [
            (  # missing function arn
                {
                    "Authorizers": {
                        "mycoolauthorizer": {
                            "FunctionPayloadType": "TOKEN",
                            "Identity": {
                                "Header": "myheader",
                            },
                        }
                    }
                },
            ),
            (  # invalid (blank) function arn
                {
                    "Authorizers": {
                        "mycoolauthorizer": {
                            "FunctionPayloadType": "TOKEN",
                            "Identity": {
                                "Header": "myheader",
                            },
                            "FunctionArn": "",
                        }
                    }
                },
            ),
            (  # not a token or request authorizer
                {
                    "Authorizers": {
                        "mycoolauthorizer": {
                            "FunctionPayloadType": "TOKEN",
                            "Identity": {
                                "Header": "myheader",
                            },
                            "FunctionArn": "function",
                            "FunctionPayloadType": "hello world",
                        }
                    }
                },
            ),
        ]
    )
    @patch("samcli.commands.local.lib.swagger.integration_uri.LambdaUri.get_function_name")
    def test_extract_invalid_authorizers_from_properties(self, properties, function_name_mock):
        logical_id = Mock()

        function_name_mock.return_value = Mock()

        collector_mock = Mock()
        collector_mock.add_authorizers = Mock()

        SamApiProvider._extract_authorizers_from_props(logical_id, properties, collector_mock, Route.API)

        collector_mock.add_authorizers.assert_called_with(logical_id, {})

    @parameterized.expand(
        [
            (  # wrong payload type
                {
                    "FunctionPayloadType": "REQUEST",
                    "Identity": {
                        "Header": "myheader",
                    },
                    "AuthorizerPayloadFormatVersion": True,
                },
                "'AuthorizerPayloadFormatVersion' must be of type string for Lambda Authorizer 'auth'.",
            ),
            (  # missing payload format version
                {
                    "FunctionPayloadType": "REQUEST",
                    "Identity": {
                        "Header": "myheader",
                    },
                },
                "Lambda Authorizer 'auth' must contain a valid 'AuthorizerPayloadFormatVersion' for HTTP APIs.",
            ),
            (  # invalid payload format version
                {
                    "FunctionPayloadType": "REQUEST",
                    "Identity": {
                        "Header": "myheader",
                    },
                    "AuthorizerPayloadFormatVersion": "invalid",
                },
                "Lambda Authorizer 'auth' must contain a valid 'AuthorizerPayloadFormatVersion' for HTTP APIs.",
            ),
            (  # simple responses using wrong format version
                {
                    "FunctionPayloadType": "REQUEST",
                    "Identity": {
                        "Header": "myheader",
                    },
                    "AuthorizerPayloadFormatVersion": "1.0",
                    "EnableSimpleResponses": True,
                },
                "EnableSimpleResponses must be used with the 2.0 payload format version in Lambda Authorizer 'auth'.",
            ),
        ]
    )
    def test_extract_invalid_http_authorizer_throws_exception(self, properties, expected_ex):
        with self.assertRaisesRegex(InvalidSamDocumentException, expected_ex):
            SamApiProvider._extract_request_lambda_authorizer("auth", "lambda", Mock(), properties, Route.HTTP)

    @parameterized.expand(
        [
            ({"Auth": {"Authorizer": "myauth"}}, "myauth", True),  # defined auth
            ({"Auth": {"Authorizer": "NONE"}}, None, False),  # explict no authorizers
            ({}, None, True),  # default auth
        ]
    )
    def test_add_authorizer_in_serverless_function(self, authorizer_obj, expected_auth_name, use_default):
        properties = {"Path": "path", "Method": "method", "RestApiId": "id"}

        if authorizer_obj:
            properties.update(authorizer_obj)

        _, route = SamApiProvider._convert_event_route(Mock(), Mock(), properties, Route.API)

        self.assertEqual(
            route, Route(ANY, ANY, ["method"], ANY, ANY, ANY, ANY, ANY, expected_auth_name, ANY, use_default)
        )


def make_swagger(routes, binary_media_types=None):
    """
    Given a list of API configurations named tuples, returns a Swagger document

    Parameters
    ----------
    routes : list of samcli.commands.local.agiw.local_agiw_service.Route
    binary_media_types : list of str

    Returns
    -------
    dict
        Swagger document

    """
    swagger = {"paths": {}, "swagger": "2.0"}

    for api in routes:
        swagger["paths"].setdefault(api.path, {})

        integration = {
            "x-amazon-apigateway-integration": {
                "type": "aws_proxy",
                "uri": "arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-1"
                ":123456789012:function:{}/invocations".format(api.function_name),  # NOQA
            }
        }
        for method in api.methods:
            if method.lower() == "any":
                method = "x-amazon-apigateway-any-method"

            swagger["paths"][api.path][method] = integration

    if binary_media_types:
        swagger["x-amazon-apigateway-binary-media-types"] = binary_media_types

    return swagger
