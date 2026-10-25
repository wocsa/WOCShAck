import os
import shlex
from datetime import datetime


def write_audit(message):
    safe = shlex.quote(str(message))
    os.system(f'echo {safe} >> /app/Activity/audit.log')


def write_activity(activity):
    with open("Activity/Activity", "a") as file:
        file.write(activity)


def write_transaction(transaction):
    with open("Activity/Transactions", "a") as file:
        file.write(transaction)


def write_error(message):
    with open("Activity/Errors", "a") as file:
        file.write(message)


def write_security(message):
    with open("Activity/Security", "a") as file:
        file.write(message)


def log(typ, **info):
    if typ == "tr":
        try:
            origin = info["origin"]
            destination = info["destination"]
            amount = info["amount"]
            write_transaction(f"{datetime.now()} Transaction: {origin} -> {destination}: {amount} Neuros\n")

        except KeyError as e:
            write_error(f"{datetime.now()} Error: No such argument {e} for type {typ}\n")

    elif typ == "adu":
        try:
            id = info["id"]
            write_activity(f"{datetime.now()} - User with ID:{id} was created\n")

        except KeyError as e:
            write_error(f"{datetime.now()} Error: No such argument {e} for type {typ}\n")

    elif typ == "delu":
        try:
            id = info["id"]
            write_activity(f"{datetime.now()} - User with ID:{id} was deleted\n")

        except KeyError as e:
            write_error(f"{datetime.now()} Error: No such argument {e} for type {typ}\n")

    elif typ == "getu":
        try:
            id = info["id"]
            write_activity(f"{datetime.now()} - User with ID:{id} was pulled\n")

        except KeyError as e:
            write_error(f"{datetime.now()} Error: No such argument {e} for type {typ}\n")

    elif typ == "ad":
        try:
            id = info["id"]
            amount = info["amount"]
            write_transaction(f"{datetime.now()} - User with ID:{id} was funded with {amount} Neuros\n")

        except KeyError as e:
            write_error(f"{datetime.now()} Error: No such argument {e} for type {typ}\n")

    elif typ == "sb":
        try:
            id = info["id"]
            amount = info["amount"]
            write_transaction(f"{datetime.now()} - User with ID:{id} account was set to {amount} Neuros\n")

        except KeyError as e:
            write_error(f"{datetime.now()} Error: No such argument {e} for type {typ}\n")

    elif typ == "sp":
        id = info["id"]
        write_activity(f"{datetime.now()} User of Id:{id}, had his PIN changed\n")

    elif typ == "sescr":
        sid = info["sid"]
        write_activity(f"{datetime.now()} Session:{sid}, created\n")

    elif typ == "sescl":
        sid = info["sid"]
        write_activity(f"{datetime.now()} Session:{sid}, closed\n")

    elif typ == "err":
        try:
            error = info["error"]
            write_error(f"{datetime.now()} - {error}\n")

        except KeyError as e:
            write_error(f"{datetime.now()} Error: No such argument {e} for type {typ}\n")

    else:
        write_error(f"{datetime.now()} Error: No such type {typ}\n")
