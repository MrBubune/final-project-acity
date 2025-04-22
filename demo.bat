@echo off
REM ————————————————————————————————
REM Demo script for secure MQTT pub/sub system
REM ————————————————————————————————

REM 1) Create the teacher1 user (password "secret")
echo secret| python -m admin.cli create-user --username teacher1 --role Teacher

REM 2) Grant wildcard ACL on school/# for both publish & subscribe
python -m admin.cli add-acl --username teacher1 --topic school/# --can-subscribe --can-publish

REM 3) Start the broker in a new console window
start "Broker" cmd /k "python -m broker.server"

REM give broker a moment to come up
timeout /t 2 >nul

REM 4) Start a subscriber at QoS 2 in a new console
start "Subscriber" cmd /k "python -m client.subscriber --client-id sub --username teacher1 --password secret --topic school/# --qos 2"

REM give subscriber time to connect
timeout /t 2 >nul

REM 5) Publish a retained message at QoS 2
python -m client.publisher --client-id pub --username teacher1 --password secret --topic school/demo --message "Hello from demo!" --qos 2 --retain

REM 6) Launch the Admin Web UI
start "Admin UI" cmd /k "python -m admin.web"

echo.
echo Demo launched:
echo  - Broker console (port 8883)
echo  - Subscriber console listening on school/# (QoS2)
echo  - Admin UI at http://127.0.0.1:5000
echo.
pause
