# -*- coding: utf-8 -*-
"""Timesheet endpoints — read/create entries on account.analytic.line.

Reminder: in Odoo, "timesheets" are not a standalone model. They live on
`account.analytic.line` rows where `project_id` is set. The native module
`hr_timesheet` extends that model with project/task fields and an elaborate
`create()` override that links employee↔user↔company and computes amounts
from `hourly_cost`. We MUST go through `env['account.analytic.line'].create()`
to keep that logic intact — direct SQL or raw writes would skip it and
break cost reporting downstream.

Route table:
    GET   /api/employee/timesheets              List entries for this employee
    POST  /api/employee/timesheets              Create a new entry ("apply")
    GET   /api/employee/timesheets/projects     Selectable projects + tasks

Security contract:
    - validate_request() at the top
    - every query domain starts with [('employee_id', '=', employee.id),
                                       ('project_id', '!=', False)]
    - the create endpoint hardcodes `employee_id = employee.id` —
      a client-supplied employee_id in the body is ignored
"""
import logging

from odoo import http, fields, SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError, AccessError
from odoo.http import request

from ..helpers import response_helper as R
from ..helpers import token_helper
from ..helpers import validators as V
from ..helpers import serializers as S

_logger = logging.getLogger(__name__)


class EmployeeTimesheetController(http.Controller):

    # =====================================================================
    # GET /api/employee/timesheets
    # =====================================================================

    @http.route(
        '/api/employee/timesheets',
        type='http',
        auth='none',
        methods=['GET', 'OPTIONS'],
        csrf=False,
        cors='*',
    )
    def list_timesheets(self, **kw):
        """List the authenticated employee's timesheet entries.

        Query parameters:
            from        YYYY-MM-DD   (default: first day of current month)
            to          YYYY-MM-DD   (default: today)
            project_id  int          (optional — filter to one project)
            task_id     int          (optional — filter to one task)
            limit       int          (default 20, max 100)
            offset      int          (default 0)

        Success response (200):
            {
                "status": "success",
                "data": [ {...timesheet...}, ... ],
                "meta": { "count": 47, "offset": 0, "limit": 20, "has_more": true }
            }
        """
        if request.httprequest.method == 'OPTIONS':
            return self._cors_preflight()

        try:
            employee, err = token_helper.validate_request()
            if err:
                return err

            date_from, date_to, date_err = V.parse_date_range(request.params)
            if date_err:
                return R.error_422(date_err)

            limit, offset = V.parse_pagination(request.params)

            # Ownership filter + 'is a timesheet, not a generic analytic line'
            domain = [
                ('employee_id', '=', employee.id),
                ('project_id', '!=', False),
                ('date', '>=', date_from.isoformat()),
                ('date', '<=', date_to.isoformat()),
            ]

            project_filter = request.params.get('project_id')
            if project_filter:
                try:
                    domain.append(('project_id', '=', int(project_filter)))
                except (ValueError, TypeError):
                    return R.error_422('project_id must be an integer.')

            task_filter = request.params.get('task_id')
            if task_filter:
                try:
                    domain.append(('task_id', '=', int(task_filter)))
                except (ValueError, TypeError):
                    return R.error_422('task_id must be an integer.')

            env = request.env(user=SUPERUSER_ID)
            total = env['account.analytic.line'].search_count(domain)
            records = env['account.analytic.line'].search(
                domain, limit=limit, offset=offset, order='date desc, id desc',
            )

            return R.success_list(
                data=S.serialize_timesheet_list(records),
                total_count=total,
                offset=offset,
                limit=limit,
            )

        except Exception as e:
            return R.error_500(exception=e)

    # =====================================================================
    # POST /api/employee/timesheets
    # =====================================================================

    @http.route(
        '/api/employee/timesheets',
        type='http',
        auth='none',
        methods=['POST', 'OPTIONS'],
        csrf=False,
        cors='*',
    )
    def apply_timesheet(self, **kw):
        """Create a new timesheet entry for the authenticated employee.

        Request body:
            {
                "project_id": 5,            (required)
                "task_id": 12,              (optional)
                "date": "2026-06-13",       (required)
                "unit_amount": 3.5,         (required — hours)
                "description": "..."        (optional)
            }

        Pre-flight validation done in Python before hitting the ORM:
            - project exists, is active, allows timesheets
            - task (if provided) belongs to the chosen project and allows
              timesheets
            - employee_id is hardcoded to self; any value in the body ignored

        Success response (201):
            {
                "status": "success",
                "data": { ...serialized timesheet... }
            }

        Error responses:
            422 — bad input
            404 — project or task doesn't exist / isn't accessible
            409 — model-level rejection (analytic account misconfig etc.)
        """
        if request.httprequest.method == 'OPTIONS':
            return self._cors_preflight()

        try:
            employee, err = token_helper.validate_request()
            if err:
                return err

            body, parse_err = V.parse_json_body()
            if parse_err:
                return R.error_400(R.ERR_VALIDATION, parse_err)

            data, val_err = V.validate_timesheet_create(body)
            if val_err:
                return R.error_422(val_err)

            env = request.env(user=SUPERUSER_ID)

            # ----- Verify project is valid and accessible -----
            project = env['project.project'].search([
                ('id', '=', data['project_id']),
                ('active', '=', True),
                ('allow_timesheets', '=', True),
            ], limit=1)
            if not project:
                return R.error_404(
                    'Project not found, archived, or does not allow timesheets.'
                )

            # ----- Verify task (if any) is on this project -----
            task = None
            if data['task_id']:
                task = env['project.task'].search([
                    ('id', '=', data['task_id']),
                    ('project_id', '=', project.id),
                    ('allow_timesheets', '=', True),
                ], limit=1)
                if not task:
                    return R.error_404(
                        'Task not found on this project or does not allow timesheets.'
                    )

            # ----- Build vals — never trust a client-sent employee_id -----
            vals = {
                'employee_id': employee.id,
                'project_id': project.id,
                'date': data['date'],
                'unit_amount': data['unit_amount'],
                'name': data['name'],
                'company_id': employee.company_id.id,
            }
            if task:
                vals['task_id'] = task.id

            # ----- Hand off to the ORM (triggers hr_timesheet's create override) -----
            try:
                line = env['account.analytic.line'].create(vals)
            except AccessError as e:
                return R.error_403(R.ERR_ACCESS_DISABLED, str(e))
            except (UserError, ValidationError) as e:
                # Common causes: missing analytic account, archived employee,
                # company mismatch between project/task/employee
                return R.error_409(str(e))

            _logger.info(
                'Timesheet entry created by employee %s (id=%d, line_id=%d, '
                'project_id=%d, task_id=%s, hours=%.2f)',
                employee.name, employee.id, line.id, project.id,
                task.id if task else 'None', data['unit_amount'],
            )

            return R.created(S.serialize_timesheet(line))

        except Exception as e:
            return R.error_500(exception=e)

    # =====================================================================
    # GET /api/employee/timesheets/projects
    # =====================================================================

    @http.route(
        '/api/employee/timesheets/projects',
        type='http',
        auth='none',
        methods=['GET', 'OPTIONS'],
        csrf=False,
        cors='*',
    )
    def list_projects(self, **kw):
        """List projects (and their tasks) selectable for new timesheet entries.

        The mobile app calls this once per session to populate the project
        and task dropdowns on the "apply timesheet" form. Tasks are embedded
        inline so the app doesn't need a follow-up request after the user
        picks a project.

        Query parameters:
            include_tasks   '0' to skip task embedding (default: '1')

        Filters applied:
            - project.active = True
            - project.allow_timesheets = True
            - project.company_id matches the employee's company
            - privacy: skip 'followers'-restricted projects the employee
              isn't a follower of

        Success response (200):
            {
                "status": "success",
                "data": [
                    {
                        "id": 5,
                        "name": "Q3 Migration",
                        "allow_timesheets": true,
                        "tasks": [ {"id": 12, "name": "Schema sync", ...}, ... ]
                    }
                ]
            }
        """
        if request.httprequest.method == 'OPTIONS':
            return self._cors_preflight()

        try:
            employee, err = token_helper.validate_request()
            if err:
                return err

            include_tasks = request.params.get('include_tasks', '1') != '0'

            env = request.env(user=SUPERUSER_ID)

            # Privacy: native ir.rule says employees can see their followed
            # private projects + all non-private ones. With sudo we can't
            # rely on the rule — replicate it in the domain.
            partner_id = employee.user_id.partner_id.id if employee.user_id else False
            privacy_clause = ['|', ('privacy_visibility', '!=', 'followers')]
            if partner_id:
                privacy_clause.append(('message_partner_ids', 'in', [partner_id]))
            else:
                # No linked user → no followed partner → only non-private projects
                privacy_clause = [('privacy_visibility', '!=', 'followers')]

            domain = [
                ('active', '=', True),
                ('allow_timesheets', '=', True),
                ('company_id', '=', employee.company_id.id),
            ] + privacy_clause

            projects = env['project.project'].search(domain, order='name asc')

            data = [
                S.serialize_project(p, include_tasks=include_tasks)
                for p in projects
            ]

            return R.success(data)

        except Exception as e:
            return R.error_500(exception=e)

    # =====================================================================
    # CORS Helper
    # =====================================================================

    def _cors_preflight(self):
        """Handle CORS preflight (OPTIONS) requests."""
        from werkzeug.wrappers import Response
        return Response(
            status=204,
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Authorization, Content-Type',
                'Access-Control-Max-Age': '86400',
            },
        )
