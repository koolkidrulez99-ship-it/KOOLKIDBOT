import copy
import hashlib
import hmac
import re
import secrets
import time

from flask import Blueprint, jsonify, request

from .bridge import Bridge, binding, hub
from .commands import CommandError, READ_ACTIONS, emergency, parse, safe_input


def register(app, namespace):
    bridge = Bridge(app, namespace)
    bp = Blueprint("ai_intelligence", __name__, url_prefix="/ai-intelligence")

    @bp.before_request
    def guard():
        try:
            cid, state = bridge.authorize()
        except CommandError as error:
            return jsonify(error=str(error)), 403
        ai = hub(state)
        if request.method != "GET":
            if request.content_length and request.content_length > 8192:
                return jsonify(error="Request too large."), 413
            if not request.is_json or not hmac.compare_digest(request.headers.get("X-AI-CSRF", ""), ai.csrf):
                return jsonify(error="Refresh the chat before sending commands."), 403
            if not isinstance(request.get_json(silent=True), dict):
                return jsonify(error="Expected a JSON object."), 400
            origin = request.headers.get("Origin")
            if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
                return jsonify(error="Cross-origin commands are not allowed."), 403

    @bp.after_request
    def private(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @bp.errorhandler(CommandError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @bp.errorhandler(Exception)
    def unexpected(error):
        # Exception strings may contain provider bodies or credentials.
        bridge.s.logger.warning("AI Intelligence request failed (%s)", type(error).__name__)
        return jsonify(error="AI Intelligence could not complete the request. Check trade history before retrying a purchase."), 500

    def current():
        cid, state = bridge.authorize()
        ai = hub(state)
        key = binding(state)
        if ai.account != key:
            ai.messages = []
            ai.previous = None
            ai.account = key
            ai.clarification = None
        return cid, state, ai

    def remember(ai, role, text):
        ai.messages.append({"role": role, "text": text})
        ai.messages = ai.messages[-40:]

    @bp.get("/state")
    def status():
        _, state, ai = current()
        context_id = hashlib.sha256(repr(binding(state)).encode()).hexdigest()[:24]
        return jsonify(csrf=ai.csrf, context_id=context_id, visible=bridge.preference(), messages=ai.messages, settings=bridge.settings(state))

    @bp.post("/preferences")
    def preferences():
        visible = (request.get_json() or {}).get("visible")
        if not isinstance(visible, bool):
            raise CommandError("Visible must be true or false.")
        return jsonify(visible=bridge.preference(visible))

    @bp.post("/clear")
    def clear():
        _, _, ai = current()
        if not ai.lock.acquire(False):
            return jsonify(error="Wait for the current action to finish."), 409
        try:
            ai.messages = []
            ai.previous = None
            ai.clarification = None
            ai.generation += 1
            return jsonify(status="cleared")
        finally:
            ai.lock.release()

    @bp.post("/command")
    def command():
        cid, state, ai = current()
        text = safe_input((request.get_json() or {}).get("message"))
        for key in ("api_token", "oauth_pending_access_token", "pat_pending_access_token"):
            secret = state.get(key)
            if isinstance(secret, str) and len(secret) >= 6 and secret in text:
                raise CommandError("Do not send credentials in chat. Use the connection field.")
        if emergency(text):
            result = bridge.stop(cid, state)
            bridge.audit({"action": "stop_all_trading"}, result)
            remember(ai, "assistant", result["message"])
            return jsonify(results=[result])
        if not ai.lock.acquire(False):
            return jsonify(error="A command is already being processed. Emergency stop remains available."), 409
        try:
            if time.monotonic() - ai.last_command < 0.6:
                return jsonify(error="Please wait a moment before sending another command."), 429
            ai.last_command = time.monotonic()
            captured = binding(state)
            generation = ai.generation
            clarification = ai.clarification
            ai.clarification = None
            if clarification and clarification["expires"] > time.monotonic() and re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)", text):
                plan = copy.deepcopy(clarification["plan"])
                plan["actions"][clarification["index"]]["barrier"] = text
            else:
                plan = parse(text, bridge.settings(state), ai.previous, ai.messages)
            try:
                actions = bridge.prepare(cid, state, plan)
            except CommandError as error:
                for index, a in enumerate(plan["actions"]):
                    if a["action"] == "place_trade" and a.get("trade_type", "").upper() in ("OVER", "UNDER", "MATCH", "MATCHES", "DIFF", "DIFFER", "DIFFERS", "HIGHER", "LOWER", "TOUCH", "NO TOUCH") and "barrier" not in a:
                        ai.clarification = {"plan": copy.deepcopy(plan), "index": index, "expires": time.monotonic() + 180}
                        remember(ai, "user", text)
                        remember(ai, "assistant", str(error))
                        break
                raise
            if binding(state) != captured or generation != ai.generation:
                raise CommandError("The account or stop state changed while preparing the command. Send it again.")
            remember(ai, "user", text)
            if all(a["action"] in READ_ACTIONS for a in actions):
                results = [bridge.read(state, a) for a in actions]
                for r in results:
                    remember(ai, "assistant", r["message"])
                return jsonify(results=results, settings=bridge.settings(state))
            # Expiring, server-owned plan. The execute endpoint accepts IDs, never action JSON.
            now = time.monotonic()
            ai.plans = {k: v for k, v in ai.plans.items() if v["expires"] > now}
            if len(ai.plans) >= 32:
                raise CommandError("Too many pending plans. Wait for older plans to expire.")
            pid = secrets.token_urlsafe(24)
            ai.plans[pid] = {"actions": actions, "original": copy.deepcopy(plan), "binding": captured,
                             "profile": state["active_profile"], "generation": generation,
                             "expires": now + 180, "next": 0, "results": {}, "awaiting_ui": None}
            bridge.audit(actions, {"status": "prepared", "plan": pid})
            return jsonify(plan_id=pid, actions=actions, execution="bounded_ordered",
                           settings=bridge.settings(state), message="Confirm these actions. Trades use separate fresh proposals and are submitted one at a time, not atomically.")
        finally:
            ai.lock.release()

    def get_plan(ai, state, body):
        pid = body.get("plan_id")
        if not isinstance(pid, str) or len(pid) > 100:
            raise CommandError("Invalid plan.")
        plan = ai.plans.get(pid)
        if not plan or plan["expires"] < time.monotonic():
            raise CommandError("This confirmation expired. Send a new command.")
        if plan["binding"] != binding(state) or plan["profile"] != state["active_profile"] or plan["generation"] != ai.generation:
            raise CommandError("Account, profile, connection or stop state changed. Prepare a new command.")
        index = body.get("index")
        if type(index) is not int or not 0 <= index < len(plan["actions"]):
            raise CommandError("Invalid action index.")
        return pid, plan, index

    @bp.post("/execute")
    def execute():
        cid, state, ai = current()
        if not ai.lock.acquire(False):
            return jsonify(error="A command is in progress."), 409
        try:
            pid, plan, index = get_plan(ai, state, request.get_json() or {})
            if index in plan["results"]:
                return jsonify(result=plan["results"][index], replay=True)
            if index != plan["next"] or plan["awaiting_ui"] is not None:
                raise CommandError("Complete the previous action first.")
            action = plan["actions"][index]
            bridge.authorize()
            # Persist intent before any side effect; a broken audit store fails closed.
            bridge.audit(action, {"status": "executing", "plan": pid, "index": index})
            result = {"status": "pending", "message": "Execution started. Check the bot before retrying."}
            plan["results"][index] = result
            try:
                if action["action"] in READ_ACTIONS:
                    result = bridge.read(state, action)
                elif action["action"] == "place_trade":
                    result = bridge.trade(cid, state, action, plan["binding"], plan["generation"])
                else:
                    result = bridge.control(cid, state, action)
            except CommandError as error:
                result = {"status": "failed", "message": str(error)}
            except Exception:
                result = {"status": "pending", "message": "Outcome could not be verified. Check the dashboard; this action will not be retried."}
            plan["results"][index] = result
            plan["next"] += 1
            plan["profile"] = state["active_profile"]
            # A failed prerequisite must never start the subsequent strategy at the wrong stake.
            if result["status"] in ("failed", "pending") and (action["action"] != "place_trade" or result["status"] == "pending"):
                plan["next"] = len(plan["actions"])
                result["halt_remaining"] = True
            if result["status"] == "ui_pending":
                plan["awaiting_ui"] = index
            if plan["next"] == len(plan["actions"]) and all(r["status"] in ("completed", "confirmed") for r in plan["results"].values()):
                ai.previous = plan["original"]
            if result.get("message"):
                remember(ai, "assistant", result["message"])
            elif result["status"] == "confirmed":
                remember(ai, "assistant", f"{result['trade_type']} placed on {result['market']}, stake {result['stake']} USD. Contract {result['contract_id']}.")
            bridge.audit(action, result)
            return jsonify(result=result, settings=bridge.settings(state))
        finally:
            ai.lock.release()

    @bp.post("/ui-result")
    def ui_result():
        _, state, ai = current()
        if not ai.lock.acquire(False):
            return jsonify(error="A command is in progress."), 409
        try:
            body = request.get_json() or {}
            _, plan, index = get_plan(ai, state, body)
            if plan["awaiting_ui"] != index:
                raise CommandError("There is no pending UI action.")
            succeeded = body.get("success") is True
            result = {"status": "completed" if succeeded else "failed", "message": "Existing martingale control updated (dashboard confirmed)." if succeeded else "The dashboard could not apply that martingale setting. Remaining actions cancelled."}
            plan["results"][index] = result
            plan["awaiting_ui"] = None
            if not succeeded:
                plan["next"] = len(plan["actions"])
                result["halt_remaining"] = True
            remember(ai, "assistant", result["message"])
            bridge.audit(plan["actions"][index], result)
            return jsonify(result=result)
        finally:
            ai.lock.release()

    app.register_blueprint(bp)
    return bridge
