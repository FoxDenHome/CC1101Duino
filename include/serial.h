#pragma once

#include <Arduino.h>

class CommandSerial {
public:
	CommandSerial(HardwareSerial& _serial);

	void init();
	void loop();

	void sendFirst(const String& text);
	void sendNext(const String& text);
	void sendEnd(const String& text);
	void send(const String& text);

	void echoFirst();
	void echoFirst(const String& text);
	void echo(const String& text);

	void sendFirst();
	void sendEnd();

protected:
	virtual void handle() = 0;

    void replyFirst();
    void replyFirst(const String& reply);
    void reply(const String& reply);

	HardwareSerial* serial;
	String buffer;
	byte commandState;
	char command;
};
