"""
skill the-cows-lists
Copyright (C) 2017  Carsten Agerskov

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import json
import sys
import os
from adapt.intent import IntentBuilder
from fuzzywuzzy import process
from mycroft import removes_context
from mycroft.skills.core import MycroftSkill
from mycroft.skills.core import intent_handler
from mycroft.util.log import getLogger
from os.path import dirname

HOME_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HOME_DIR)
import cow_rest

__author__ = 'cagerskov'

TASK_PARAMETER = "taskName"
LIST_PARAMETER = "listName"
BEST_MATCH_PARAMETER = "bestMatch"
ERROR_TEXT_PARAMETER = "errorText"
ERROR_CODE_PARAMETER = "errorCode"
FUNCTION_NAME_PARAMETER = "functionName"
LINE_PARAMETER = "lineNumber"
NOF_TASK_PARAMETER = "nofTask"
UNDO_CONTEXT = "UndoContext"
CONFIRM_CONTEXT = "ConfirmContext"

LOGGER = getLogger(__name__)


class CowsLists(MycroftSkill):
    def __init__(self):
        super(CowsLists, self).__init__(name="TheCowsLists")
        self.stopSpeaking = False

    def initialize(self):
        self.load_data_files(dirname(__file__))

    def get_config(self):
        try:
            try:
                if not cow_rest.api_key:
                    cow_rest.api_key = self.config.get('api_key')
            except AttributeError:
                cow_rest.api_key = self.settings.get('api_key')

            try:
                if not cow_rest.secret:
                    cow_rest.secret = self.config.get('secret')
            except AttributeError:
                cow_rest.secret = self.settings.get('secret')

            if not cow_rest.api_key or not cow_rest.secret:
                raise Exception("api key or secret not configured")

            return True

        except Exception as e:
            self.speak_dialog('ConfigNotFound')
            return False

    def operation_init(self):
        if not self.get_config():
            return False

        cow_rest.get_token(cow_rest)

        if not cow_rest.auth_token and cow_rest.frob:
            self.speak_dialog("InAuthentication")
            return False

        if not cow_rest.auth_token:
            self.speak_dialog("NotAuthenticated")
            return False

        return True

    def add_task_to_list(self, task_name, list_name, list_id):
        taskseries_id, task_id, error_text, error_code = cow_rest.add_task(task_name, list_id)
        if error_text:
            self.speak_dialog('RestResponseError',
                              {ERROR_TEXT_PARAMETER: error_text,
                               ERROR_CODE_PARAMETER: error_code})

            return False

        self.speak_dialog("AddTaskToList", {TASK_PARAMETER: task_name, LIST_PARAMETER: list_name})
        c = {"dialog": "AddTaskToListUndo",
             "dialogParam": {TASK_PARAMETER: task_name, LIST_PARAMETER: list_name},
             "task": {"task_id": task_id,
                      "task_name": task_name,
                      "taskseries_id": taskseries_id,
                      "list_id": list_id,
                      "list_name": list_name}}

        self.set_context(UNDO_CONTEXT, json.dumps(c))

        return True

    def find_list(self, list_name):
        list_result, error_text, error_code = cow_rest.get_list()

        if error_text:
            return None, None, None, error_text, error_code

        # Workaround the intent parser remove the word list: First, try to match to a "list_name list"
        list_name_best_match, significance = process.extractOne(list_name + " list",
                                                                map(lambda x: str(x['name']).lower(),
                                                                    list_result))

        # Then try to match to "list_name"
        if significance < 100:
            list_name_best_match, significance = process.extractOne(list_name,
                                                                    map(lambda x: str(x['name']).lower(),
                                                                        list_result))

        list_id = filter(lambda x: str(x['name']).lower() == list_name_best_match, list_result)[0]['id']

        return list_name_best_match, list_id, significance, error_text, error_code

    @intent_handler(IntentBuilder("AuthenticateIntent").require("AuthenticateKeyword").build())
    @removes_context(UNDO_CONTEXT)
    @removes_context(CONFIRM_CONTEXT)
    def authenticate_intent(self):
        try:
            if not self.get_config():
                return

            cow_rest.get_token(cow_rest)

            if cow_rest.auth_token:
                error_text, error_code = cow_rest.verify_token_validity()
                if not error_text:
                    self.speak_dialog("TokenValid")
                    return

            error_text, error_code = cow_rest.get_frob(cow_rest)
            if error_text:
                self.speak_dialog('RestResponseError',
                                  {ERROR_TEXT_PARAMETER: error_text,
                                   ERROR_CODE_PARAMETER: error_code})
                return

            auth_url = cow_rest.get_auth_url()

            mail_body = "Use the link below to authenticate Mycroft with remember the milk.<br>" \
                        + "After authentication, say: Hey Mycroft, get a token for remember the milk<br><br>" \
                        + '<a href = "' + auth_url + '">' + auth_url + '</a>'

            self.send_email("Authentication", mail_body)
            self.speak_dialog("EmailSent")

        except Exception as e:
            LOGGER.exception("Error in authenticate_intent: {0}".format(e))
            self.speak_dialog('GeneralError',
                              {FUNCTION_NAME_PARAMETER: "authenticate intent",
                               LINE_PARAMETER: format(sys.exc_info()[-1].tb_lineno)})

    @intent_handler(IntentBuilder("GetTokenIntent").require("GetTokenKeyword").build())
    @removes_context(UNDO_CONTEXT)
    @removes_context(CONFIRM_CONTEXT)
    def get_token_intent(self):
        try:
            if not self.get_config():
                return

            cow_rest.get_token(cow_rest)

            if cow_rest.auth_token:
                error_text, error_code = cow_rest.verify_token_validity()
                if error_text and error_code != '98':
                    self.speak_dialog('RestResponseError',
                                      {ERROR_TEXT_PARAMETER: error_text,
                                       ERROR_CODE_PARAMETER: error_code})
                    return

                if not error_text:
                    self.speak_dialog("TokenValid")
                    return

            if not cow_rest.frob:
                self.speak_dialog('AuthenticateBeforeToken')
                return

            error_text, error_code = cow_rest.get_new_token(cow_rest)
            if error_text:
                self.speak_dialog('RestResponseError',
                                  {ERROR_TEXT_PARAMETER: error_text,
                                   ERROR_CODE_PARAMETER: error_code})
                return

            self.speak_dialog("GotToken")

        except Exception as e:
            LOGGER.exception("Error in get_token_intent: {0}".format(e))
            self.speak_dialog('GeneralError',
                              {FUNCTION_NAME_PARAMETER: "get token intent",
                               LINE_PARAMETER: format(sys.exc_info()[-1].tb_lineno)})

    @intent_handler(IntentBuilder("AddTaskToListIntent").require("AddTaskToListKeyword").require(TASK_PARAMETER).
                    require(LIST_PARAMETER).build())
    def add_task_to_list_intent(self, message):
        try:
            self.remove_context(UNDO_CONTEXT)
            self.remove_context(CONFIRM_CONTEXT)
            task_name = message.data.get(TASK_PARAMETER)
            list_name = message.data.get(LIST_PARAMETER)

            if not self.operation_init():
                return

            error_text, error_code = cow_rest.get_timeline(cow_rest)
            if error_text:
                self.speak_dialog('RestResponseError',
                                  {ERROR_TEXT_PARAMETER: error_text,
                                   ERROR_CODE_PARAMETER: error_code})
                return

            list_name_best_match, list_id, significance, error_text, error_code = self.find_list(list_name)
            if error_text:
                self.speak_dialog('RestResponseError',
                                  {ERROR_TEXT_PARAMETER: error_text,
                                   ERROR_CODE_PARAMETER: error_code})
                return

            if significance < 100:
                c = {"dialog": "AddTaskToList",
                     "dialogParam": {TASK_PARAMETER: task_name, LIST_PARAMETER: list_name_best_match},
                     "task": {"task_name": task_name,
                              "list_id": list_id,
                              "list_name": list_name_best_match}}

                self.set_context(CONFIRM_CONTEXT, json.dumps(c))
                self.speak_dialog("AddTaskToListMismatch",
                                  {LIST_PARAMETER: list_name, BEST_MATCH_PARAMETER: list_name_best_match})
                return

            self.add_task_to_list(task_name, list_name_best_match, list_id)

        except Exception as e:
            LOGGER.exception("Error in add_task_to_list_intent: {0}".format(e))
            self.speak_dialog('GeneralError',
                              {FUNCTION_NAME_PARAMETER: "add task to list intent",
                               LINE_PARAMETER: format(sys.exc_info()[-1].tb_lineno)})

    @intent_handler(IntentBuilder("ReadListIntent").require("ReadListKeyword").require(LIST_PARAMETER).build())
    def read_list_intent(self, message):
        try:
            list_name = message.data.get(LIST_PARAMETER)

            if not self.operation_init():
                return

            list_name_best_match, list_id, significance, error_text, error_code = self.find_list(list_name)
            if error_text:
                self.speak_dialog('RestResponseError',
                                  {ERROR_TEXT_PARAMETER: error_text,
                                   ERROR_CODE_PARAMETER: error_code})
                return

            task_list, error_code, error_text = cow_rest.list_task("status:incomplete", list_id)
            if error_text:
                self.speak_dialog('RestResponseError',
                                  {ERROR_TEXT_PARAMETER: error_text,
                                   ERROR_CODE_PARAMETER: error_code})
                return

            simple_task_list = cow_rest.simple_task_list(task_list)

            self.speak_dialog("ReadListOneItem" if len(simple_task_list) == 1 else "ReadList",
                              {LIST_PARAMETER: list_name_best_match,
                               NOF_TASK_PARAMETER: str(len(simple_task_list)) })

            map(lambda x: self.speak(x), simple_task_list)

        except Exception as e:
            LOGGER.exception("Error in read_list_intent: {0}".format(e))
            self.speak_dialog('GeneralError',
                              {FUNCTION_NAME_PARAMETER: "read list intent",
                               LINE_PARAMETER: format(sys.exc_info()[-1].tb_lineno)})


    # RTM can roll back some operations, other has to be compensated. The undo itent hides this complexity
    @intent_handler(IntentBuilder("UndoIntent").require("UndoKeyword").require(UNDO_CONTEXT).build())
    @removes_context(UNDO_CONTEXT)
    def undo_intent(self, message):
        try:
            c = json.loads(message.data.get(UNDO_CONTEXT))
            if str(c['dialog']) == "AddTaskToListUndo":
                transaction_id, error_text, error_code = cow_rest.delete_task(c['task']['task_id'],
                                                                              c['task']["taskseries_id"],
                                                                              c['task']["list_id"])

                if error_text:
                    self.speak_dialog('RestResponseError',
                                      {ERROR_TEXT_PARAMETER: error_text,
                                       ERROR_CODE_PARAMETER: error_code})
                    return

                self.speak_dialog(c['dialog'], c['dialogParam'])

        except Exception as e:
            LOGGER.exception("Error in undo_intent: {0}".format(e))
            self.speak_dialog('GeneralError',
                              {FUNCTION_NAME_PARAMETER: "undo intent",
                               LINE_PARAMETER: format(sys.exc_info()[-1].tb_lineno)})

    @intent_handler(IntentBuilder("ConfirmIntent").require("YesKeyword").require("ConfirmContext").build())
    def confirm_intent(self, message):
        self.remove_context(CONFIRM_CONTEXT)
        try:
            c = json.loads(message.data.get(CONFIRM_CONTEXT))
            if str(c['dialog']) == "AddTaskToList":
                self.add_task_to_list(c['task']['task_name'], c['task']['list_name'], c['task']['list_id'])

        except Exception as e:
            LOGGER.exception("Error in confirm_intent: {0}".format(e))
            self.speak_dialog('GeneralError',
                              {FUNCTION_NAME_PARAMETER: "confirm intent",
                               LINE_PARAMETER: format(sys.exc_info()[-1].tb_lineno)})

    @intent_handler(IntentBuilder("NoConfirmIntent").require("NoKeyword").require("ConfirmContext").build())
    @removes_context(CONFIRM_CONTEXT)
    def no_confirm_intent(self):
        self.speak_dialog('NoConfirm')

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait()
            self.speak_dialog('Stop')

def create_skill():
    return CowsLists()
