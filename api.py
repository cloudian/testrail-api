"""
    testrail api methods
"""
# pylint: disable=line-too-long, invalid-name, trailing-whitespace
# API is described here: http://docs.gurock.com/testrail-api2/start
import time
import urllib.request
import urllib.error
import json
import base64

import configparser

import logging

# Configuration
conf = configparser.ConfigParser()
with open("config", "r") as f:
    conf.read_file(f)

LOGFILE = conf.get('api_logging', 'file')
LOGLEVEL = conf.get('api_logging', 'level')

print("API Logging level: ", end='')
if LOGLEVEL == "info":
    LEVEL = logging.INFO
    print("info", end='')
elif LOGLEVEL == "debug":
    LEVEL = logging.DEBUG
    print("debug", end='')
elif LOGLEVEL == "error":
    LEVEL = logging.ERROR
    print("error", end='')
print(" (logfile: {0})".format(LOGFILE))

logger = logging.getLogger(__name__)
logger.setLevel(LEVEL)
fh = logging.FileHandler(LOGFILE)
formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)

class Client:
    """ testrail API client wrapper """
    def __init__(self, base_url, project_id, user=None, password=None):
        if user:
            self.user = user
        else:
            self.user = ''
        if password:
            self.password = password
        else:
            self.password = ''
        assert base_url, "base_url has to be supplied"
        assert project_id, "project_id has to be supplied"
        self.project_id = project_id
        if not base_url.endswith('/'):
            base_url += '/'
        self.__url = base_url + 'index.php?/api/v2/'


        if not (self.user and self.password):
            logger.warning("[testrail api init] username and password are not defined")
            self.statuses = {}
        else:
            # Retrieve status codes
            self.statuses = self.get_statuses()

    def __send_request(self, http_method, uri, data):
        """ Send a request to URI with the given http method and data
        """
        url = self.__url + uri
        
        request = urllib.request.Request(url)
        if http_method == 'POST':
            logger.debug("[api.__send_request] %s %s %s", http_method, url, data)
            request.data = bytes(json.dumps(data), 'utf-8')
        else:
            logger.debug("[api.__send_request] %s %s", http_method, url)
        auth = str(
            base64.b64encode(
                bytes('%s:%s' % (self.user, self.password), 'utf-8')
            ),
            'ascii'
        ).strip()
        request.add_header('Authorization', 'Basic %s' % auth)
        request.add_header('Content-Type', 'application/json')

        done = False
        maxtries = 5
        while not done and maxtries > 0:
            try:
                request = urllib.request.urlopen(request)
                status_code = request.getcode()
                response = request.read()
                done = True
            except urllib.error.HTTPError as exception:
                status_code = exception.code
                response = exception.read()
                if status_code == 429:
                    try:
                        sleep_time = request.headers['Retry-After']
                    except KeyError:
                        logger.debug("[api.__send_request] KeyError Exception while reading Retry-After header. Available headers: %s", request.headers.items())
                        sleep_time = 60
                    logger.debug("[api.__send_request] sleeping {0} second{1} because of a 429 error (too many requests) and retrying").format(sleep_time, "s" if sleep_time > 1 else "")
                    time.sleep(sleep_time)
                else:
                    logger.debug("[api.__send_request] got a %s error, not retrying", status_code)
                    maxtries = -1
            maxtries -= 1

        if maxtries < 0:
            logger.error("[api.__send_request] failed %s to %s, status code: %s", http_method, url, status_code)
            return None

        try:
            result = json.loads(response.decode())
        except ValueError:
            if status_code != 200 or response:
                logger.error("[api __send_request] Invalid json returned, HTTP code %s, data: %s", status_code, response)
                raise APIError("TestRail API returned invalid json, HTTP code %s, data: %s" % status_code, response)
            result = {}

        if 'error' in result:
            error = '"' + result['error'] + '"'
            raise APIError("TestRail API returned error: %s" % error)

        return result

    def send_get(self, uri):
        """ send a GET request and returns the json as a python dict

        Parameters
        ----------
        uri :
            API method to call including parameters
        """
        return self.__send_request('GET', uri, None)

    def send_post(self, uri, data):
        """ send a POST request and returns the json as a python dict
        Parameters
        ----------
        uri :
            API method to call including parameters
        data :
            json (python dict) with POST parameters
        Returns
        -------
        out
            dict containing request answer
        """
        #TODO: some api calls (such as delete_secton) use POST but send no data, triggering this
        #if not data:
        #    logger.info("[APIClient.send_post (%s)] no data provided.", uri) 
        return self.__send_request('POST', uri, data)

    # Projects methods
    def get_project(self):
        """ get_project method: gets project_id

        http://docs.gurock.com/testrail-api2/reference-projects#get_project

        Returns
        -------
        out : info about the project defined in self.project_id
        """
        method = "get_project"
        uri = "{0}/{1}".format(method, self.project_id)
        return self.send_get(uri)

    def get_projects(self):
        """ get_projects method: gets all projects

            http://docs.gurock.com/testrail-api2/reference-projects#get_projects
        """
        return self.send_get("get_projects")

    def print_info(self):
        """ print some info """
        print("project_id: ", self.project_id)
        if self.statuses:
            print("Available statuses:")
            print("id   Label")
            for status in self.statuses:
                print("{0}    {1}".format(status['id'], status['label']))

    # Results methods
    def get_results(self, test_id):
        """ get_result API method: get list

        http://docs.gurock.com/testrail-api2/reference-results#get_results
        Parameters
        ----------
        test_id
            id of the test
        Returns
        --------
        dict
            information about test_id
        """
        uri = "get_results/{0}".format(test_id)
        return self.send_get(uri)

    def add_result_for_case(self, case_id, run_id, status_id, **kwargs):
        """ add_result_for_case method: adds results to test corresponding to case_id of run_id

        http://docs.gurock.com/testrail-api2/reference-results#add_result_for_case

        Parameters
        ---------
        comment : str
            The comment / description for the test result
        version : str
            The version or build you tested against
        elapsed : timespan
            The time it took to execute the test, e.g. "30s" or "1m 45s"
        defects : str or list of str
            A comma-separated list of defects to link to the test result
        assignedto_id : The ID of a user the test should be assigned to

        Returns
        -------
        dict
            response of the add_result_for_case method
        """
        method = "add_result_for_case"
        uri = "{0}/{1}/{2}".format(method, run_id, case_id)
        data = {
            'status_id': status_id
        }

        for key in kwargs:
            if key == "defects":
                if isinstance(kwargs[key], list):
                    kwargs[key] = ",".join(kwargs[key])
            data[key] = kwargs[key]
        return self.send_post(uri, data)

    # Suites metods
    def get_suites(self):
        """ get_suites API method: retrieve list of suites for project_id

        http://docs.gurock.com/testrail-api2/reference-suite#get_suites

        Returns
        -------
        dict
            response of the get_suite method
        """
        uri = "get_suite/{0}".format(self.project_id)
        return self.send_get(uri)

    def get_suite(self, suite_id):
        """ get_result API method
                suite_id: int
            http://docs.gurock.com/testrail-api2/reference-suite#get_suite
        """
        uri = "get_suite/{0}".format(suite_id)
        return self.send_get(uri)

    def add_suite(self, name, description=None):
        """ add_suite API method: create a new test suite

        http://docs.gurock.com/testrail-api2/reference-suite#add_suite
        Parameters
        ---------
        name : str
            name of the test suite
        description : str (optional)
            description of the suite
        Returns
        -------
        dict
            response of the add_suite method. Key 'suite_id' contains
            the id of the newly added suite.
        """
        method = "add_suite"
        uri = "{0}/{1}".format(method, self.project_id)
        data = {
            "name": name
        }
        if description:
            data['description'] = description
        return self.send_post(uri, data)

    def update_suite(self, suite_id, name, description=None):
        """ update_suite API method: update an existing test suite

        http://docs.gurock.com/testrail-api2/reference-suite#update_suite
        Parameters
        ---------
        suite_id : int
            id of the suite
        name : str
            name of the test suite
        description : str (optional)
            description
        Returns
        -------
        dict
            response of the update_suite method
        """
        method = "update_suite"
        uri = "{0}/{1}".format(method, suite_id)
        data = {
            "name": name
        }
        if description:
            data['description'] = description
        self.send_post(uri, data)

    # Runs methods
    def get_run(self, run_id):
        """ get_run method: get run run_id

        http://docs.gurock.com/testrail-api2/reference-runs#get_run
        Parameters
        ---------
        run_id : int
            id of the run
        Returns
        -------
        dict
            response of the get_run method
        """
        method = "get_run"
        uri = "{0}/{1}".format(method, run_id)
        return self.send_get(uri)

    def get_runs(self, **kwargs):
        """ get_runs method: gets list of runs

        http://docs.gurock.com/testrail-api2/reference-runs#get_runs
        Parameters (optional, if none is supplied, all the runs for self.project_id are returned)
        ----------
        suite_id : int
            filter by suite
        created_after : int
            timestamp
        created_before : int
            timestamp
        created_by : int (or list of ints)
            filter run by id (or ids) of the run creators
        is_completed : bool
            filter by completion status: True (only completed) or False (only active)
        limit : int
            limit the number of returned runs
        offset : int
            skip the first 'offset' results
        milestone_id : int
            filter by milestone

        Results
        ------
        dict,
            result of the get_runs method
        """
        method = "get_runs"
        uri = "{0}/{1}".format(method, self.project_id)

        for key in kwargs:
            if key == "is_completed":
                if kwargs[key] is True:
                    uri += "&is_completed=1"
                elif kwargs[key] is False:
                    uri += "&is_completed=9"
                else:
                    raise Exception("is_completed must be bool (True or False)")
                continue
            if isinstance(kwargs[key], list):
                kwargs[key] = ",".join(kwargs[key])
            uri += "&{0}={1}".format(key, kwargs[key])
        return self.send_get(uri)

    def add_run(self, suite_id, name, **kwargs):
        """ add_suite API method: create a new test suite
        http://docs.gurock.com/testrail-api2/reference-runs#add_run

        Parameters
        -----------
        suite_id : int
            id of the test suite on which the run is based
        name : str
            name of run
        description : str (optional)
            description
        milestone_id : int
            id of the milestone the run belongs to
        assignedto_id : int
            id of the user the run is assigned to
        include_all: bool
            include all cases
        case_ids : list (optional, required if include_all=False)
            list of case ids for custom case selection

        Returns
        -------
        dict
            result of the add_run method. Key 'run_id' contains the ID of the newly created run
        """
        method = "add_run"
        uri = "{0}/{1}".format(method, self.project_id)
        data = {
            "suite_id": suite_id,
            "name": name,
        }
        for key in kwargs:
            if isinstance(kwargs[key], list):
                kwargs[key] = ",".join(kwargs[key])
            data[key] = kwargs[key]
        return self.send_post(uri, data)

    def update_run(self, run_id, description=None, case_ids=None):
        """ update_run API method: update an existing run

        http://docs.gurock.com/testrail-api2/reference-runs#add_run

        Parameters
        ----------
        run_id : int
            id of the run to update
        description : string (optional)
            new description for the run
        case_ids : list
            case ids for custom case selection

        Returns
        -------
        dict
            result of the update_run method
        """
        if not description or case_ids:
            raise Exception("[update_run] Either description or case_ids has to be supplied")

        method = "update_run"
        uri = "{0}/{1}".format(method, run_id)

        data = {}
        if description:
            data['description'] = description
        if case_ids:
            data['case_ids'] = case_ids
        else:
            data['include_all'] = True
        return self.send_post(uri, data)

    def close_run(self, run_id):
        """ close_run API method: close an existing run

        http://docs.gurock.com/testrail-api2/reference-runs#close_run

        Parameters
        ----------
        run_id : int
            id of the run to update

        Returns
        -------
        dict
            result of the close_run method, same response format as get_run()
        """
        method = "close_run"
        uri = "{0}/{1}".format(method, run_id)
        data = {}

        return self.send_post(uri, data)

    # plans methods
    def get_plan(self, plan_id):
        """ get_plan method: get plan plan_id
                plan_id: int
            http://docs.gurock.com/testrail-api2/reference-plans#get_plan
        """
        method = "get_plan"
        uri = "{0}/{1}".format(method, plan_id)
        return self.send_get(uri)

    def get_plans(self, **kwargs):
        """ get_plans method: gets list of plans

        http://docs.gurock.com/testrail-api2/reference-plans#get_plans
        Parameters
        ----------
        created_after : timestamp
        created_before : timestamp
        created_by : int or list of ints
        is_completed : bool
            True (only completed) or False (only active)
        limit : int
        offset : int
        milestone_id : int

        Returns
        -------
        dict
            output of get_plans method
        """
        method = "get_plans"
        uri = "{0}/{1}".format(method, self.project_id)
        for key in kwargs:
            if key is "is_completed":
                if kwargs[key] is True:
                    uri += "&is_completed=1"
                elif kwargs[key] is False:
                    uri += "&is_completed=0"
                else:
                    raise Exception("is_completed must be bool (True or False)")
                continue
            if isinstance(kwargs[key], list):
                kwargs[key] = ",".join(kwargs[key])
            uri += "&{0}={1}".format(key, kwargs[key])
        return self.send_get(uri)

    def add_plan(self, name, description=None, milestone_id=None, entries=None):
        """ add_plan API method

        http://docs.gurock.com/testrail-api2/reference-plans#add_plan

        Parameters
        ----------
        name : str
            name of the new test plan
        description : str (optional)
            description of the new test plan
        milestone_id : int (optional)
            id of the milestone associated with the test plan
        entries : list of dicts
            list of entries associated with the test plan, example:
                entries = [ { "suite_id": 1,
                                "name": "Custom run name",
                                ...
                            }, ...]
        See the add_plan_entry method

        Returns
        -------
        out : dict
            output of the add_plan API method
        """
        method = "add_plan"
        uri = "{0}/{1}".format(method, self.project_id)
        data = {
            "name": name,
        }
        if description:
            data['description'] = description
        if milestone_id:
            data['milestone_id'] = milestone_id
        if entries:
            assert isinstance(entries, list), "entries must be a list of dicts"
            assert all([isinstance(entry, dict) for entry in entries]), "entries must be a list of dicts"
            data['entries'] = entries
        return self.send_post(uri, data)

    def add_plan_entry(self, plan_id, suite_id, **kwargs):
        """ add_plan API method

        http://docs.gurock.com/testrail-api2/reference-plans#add_plan

        Parameters
        ----------
        plan_id : int (required)
            id of the test plan to add test run to
        suite_id : int (required)
            The ID of the test suite for the test run(s) (required)
        name : string
            The name of the test run(s)
        description : string
            The description of the test run(s) (requires TestRail 5.2 or later)
        assignedto_id : int
            The ID of the user the test run(s) should be assigned to
        include_all : bool
            True for including all test cases of the test suite and
            False for a custom case selection (default: True)
        case_ids : list
            Case IDs for the custom case selection
        config_ids : list
            List of configuration IDs used for the test runs of the test plan entry (requires TestRail 3.1 or later)
        runs : list of dicts
            test runs with configurations, example:
                runs = [ { "include_all": false,
                           "case_ids": [1, 2, 3],
                           "config_ids": [2, 5], ... },
                       ...]
        See the examples in API documentation

        Returns
        -------
        out : dict
            output of the add_plan_entry API method
        """
        method = "add_plan_entry"
        uri = "{0}/{1}".format(method, plan_id)
        data = {
            "suite_id": suite_id
        }

        for key in kwargs:
            if isinstance(kwargs[key], list):
                kwargs[key] = ", ".join(kwargs[key])
            else:
                data[key] = kwargs[key]
        return self.send_post(uri, data)

    def update_plan(self, stuff):
        """ Update existing plan """
        raise NotImplementedError("Not implemented")

    # tests methods
    def get_test(self, test_id):
        """ get_test method: get test test_id
                test_id: int
            http://docs.gurock.com/testrail-api2/reference-tests#get_test
        """
        method = "get_test"
        uri = "{0}/{1}".format(method, test_id)
        return self.send_get(uri)

    def get_tests(self, run_id, status_id=None):
        """ get_tests API method
                run_id: int, or list of ints the ID of the test run
                status_id: int, or list of ints. see self.statuses for definitions

        http://docs.gurock.com/testrail-api2/reference-tests#get_tests
        """
        method = "get_tests"
        uri = "{0}/{1}".format(method, run_id)

        if status_id:
            assert any([isinstance(status_id, list), isinstance(status_id, int)]), "status_id must be an int or a list of ints"
            if isinstance(status_id, list):
                assert all([isinstance(tmp_id, int) for tmp_id in status_id]), "status_id must be an int or a list of ints"
                uri += "&status_id={}".format(",".join(status_id))
            else:
                uri += "&status_id={}".format(status_id)
        return self.send_get(uri)

    # sections methods
    def get_section(self, section_id):
        """ get_section method: get section sectio
        \n_id
                section_id: int
            http://docs.gurock.com/sectionrail-api2/reference-sections#get_section
        """
        method = "get_section"
        uri = "{0}/{1}".format(method, section_id)
        return self.send_get(uri)

    def get_sections(self, suite_id):
        """ get_sections API method

        http://docs.gurock.com/testrail-api2/reference-sections#get_sections

        Parameters
        ----------
        suite_id : int
            id of the suite from which to retrieve sections

        Returns
        --------
        dict
            result of the get_sections method
        """
        method = "get_sections"
        uri = "{0}/{1}&suite_id={2}".format(method, self.project_id, suite_id)
        return self.send_get(uri)

    def delete_section(self, section_id):
        """ delete_section API method

        http://docs.gurock.com/testrail-api2/reference-sections#delete_sections

        Parameters
        ----------
        section_id : int
            id of the section to delete

        Returns
        --------
        dict
            result of the delete_section method
        """
        method = "delete_section"
        uri = "{0}/{1}".format(method, section_id)

        return self.send_post(uri, {})

    def add_section(self, suite_id, name, description=None, parent_id=None):
        """ add_section API method
                suite_id: int
                name: str, name of the section to be added
                description: str, optional description for the section
                parent_id: int, id of the parent section
        http://docs.gurock.com/testrail-api2/reference-sections#add_section
        """
        method = "add_section"
        uri = "{0}/{1}".format(method, self.project_id)

        data = {
            "suite_id": suite_id,
            "name": name,
        }
        if description:
            data["description"] = description
        if parent_id:
            data["parent_id"] = parent_id
        return self.send_post(uri, data)

    # cases methods
    def get_case(self, case_id):
        """ get_case API method
                case_id: int
        http://docs.gurock.com/testrail-api2/reference-cases#get_case
        """
        method = "get_case"
        uri = "{0}/{1}".format(method, case_id)
        return self.send_get(uri)

    def get_cases(self, suite_id, section_id=None):
        """ get_sections API method

        Parameters
        ----------
        suite_id : int
            id of the suite from which cases are retrieved
        Optional Parameters (for filtering)
        ----------------------------------
        section_id : int
            id of the section to filter cases by
        created_after : timestamp
            Only return test cases created after this date (as UNIX timestamp).
        created_before : timestamp
            Only return test cases created before this date (as UNIX timestamp).
        created_by : int or list of int
            A comma-separated list of creators (user IDs) to filter by.
        milestone_id : int or list of ints
            A comma-separated list of milestone IDs to filter by (not available if the milestone field is disabled for the project).
        priority_id :
            A comma-separated list of priority IDs to filter by.
        template_id :
            A comma-separated list of template IDs to filter by (requires TestRail 5.2 or later)
        type_id : int or list of ints
            A comma-separated list of case type IDs to filter by.
        updated_after : timestamp
            Only return test cases updated after this date (as UNIX timestamp).
        updated_before : timestamp
            Only return test cases updated before this date (as UNIX timestamp).
        updated_by : int or list of ints
            A comma-separated list of users who updated test cases to filter by.
        Results
        ------
        list :
            an array of test cases dicts, using the same syntax as the get_case method

        http://docs.gurock.com/testrail-api2/reference-cases#get_cases
        """
        logger.error("[api.Client.get_cases] case filtering is not yet implemented. Please fix me")
        method = "get_cases"
        uri = "{0}/{1}&suite_id={2}".format(method, self.project_id, suite_id)
        if section_id:
            uri += "&section_id={0}".format(section_id)

        return self.send_get(uri)

    def add_case(self, section_id, title, **kwargs):
        """ add_case API method
        Parameters
        ----------
        section_id: int
            The ID of the section the test case should be added to
        title: str
            The title of the test case (required)
        template_id: int
            The ID of the template (field layout) (requires TestRail 5.2 or later)
        type_id: int
            The ID of the case type
        priority_id: int
            The ID of the case priority
        estimate: str
            The estimate, e.g. "30s" or "1m 45s"
        milestone_id: int
            The ID of the milestone to link to the test case
        refs: list
            references/requirements
        keywords : list
            custom testrail field: custom_testcasecloudiankeyword

        http://docs.gurock.com/testrail-api2/reference-cases#add_case
        """
        method = "add_case"
        uri = "{0}/{1}".format(method, section_id)

        data = {
            'title': title
        }

        if "keywords" in kwargs:
            assert isinstance(kwargs["keywords"], list), "keywords must be a list of strings"

        for key in kwargs:
            if isinstance(kwargs[key], list):
                kwargs[key] = ", ".join(kwargs[key])
            else:
                data[key] = kwargs[key]
        return self.send_post(uri, data)

    def update_case(self, case_id, **kwargs):
        """ add_case API method
        Parameters
        ----------
        case_id: int
            The ID of the test case
        title: str
            The title of the test case (required)
        template_id: int
            The ID of the template (field layout) (requires TestRail 5.2 or later)
        type_id: int
            The ID of the case type
        priority_id: int
            The ID of the case priority
        estimate: str
            The estimate, e.g. "30s" or "1m 45s"
        milestone_id: The ID of the milestone to link to the test case
        refs: list
            references/requirements
        keywords : list
            custom testrail field: custom_testcasecloudiankeyword

        http://docs.gurock.com/testrail-api2/reference-cases#update_case
        """
        method = "update_case"
        uri = "{0}/{1}".format(method, case_id)

        data = {}

        for key in kwargs:
            if isinstance(kwargs[key], list):
                kwargs[key] = ", ".join(kwargs[key])
            else:
                data[key] = kwargs[key]
        return self.send_post(uri, data)

    def delete_case(self, case_id):
        """ delete_case API method

        http://docs.gurock.com/testrail-api2/reference-case#delete_case

        Parameters
        ----------
        case_id : int
            id of the case to delete

        Returns
        --------
        dict
            result of the delete_case method
        """
        method = "delete_case"
        uri = "{0}/{1}".format(method, case_id)
        return self.send_get(uri)

    # results methods
    def add_results_for_cases(self, run_id, results):
        """ add_result_for_cases API method
                run_id: int, The ID of the run for which the test cases results should be added to
                results: array of dict with case_id, status_id (comment, assignee, defect and other fields are optional)
                	"results": [
                		{
                			"case_id": 1,
                			"status_id": 5,
                			"comment": "This test failed",
                			"defects": "TR-7"

                		},
                		{
                			"case_id": 2,
                			"status_id": 1,
                			"comment": "This test passed",
                			"elapsed": "5m",
                			"version": "1.0 RC1"
                		},

                		..

                		{
                			"case_id": 1,
                			"assignedto_id": 5,
                			"comment": "Assigned this test to Joe"
                		}

                		..
                	]

            http://docs.gurock.com/testrail-api2/reference-results#add_result_for_case
        """
        method = "add_results_for_cases"
        uri = "{0}/{1}".format(method, run_id)

        data = {
            'results': results
        }

        return self.send_post(uri, data)

    # Misc methods
    def get_statuses(self):
        """ get_statuses method: get test status definitions
            http://docs.gurock.com/testrail-api2/reference-statuses
        """
        method = "get_statuses"
        uri = "{0}".format(method)
        return self.send_get(uri)

    def status_id_to_str(self, status_id):
        """ Returns a string description from status_id (int)"""
        for status in self.statuses:
            if int(status['id']) == int(status_id):
                return status['label'] # or name?
        raise APIError("The given status code is not defined")

class APIError(Exception):
    """ Basic API Exception """
    pass

def main():
    """ Basic testing of the API (login + some info)"""
    URL = conf.get("testrail", "base_url")

    client = Client(URL, project_id=conf.get("testrail", "project_id"), user=conf.get("testrail", "user"), password=conf.get("testrail", "password"))
    client.print_info()

if __name__ == '__main__':
    main()
