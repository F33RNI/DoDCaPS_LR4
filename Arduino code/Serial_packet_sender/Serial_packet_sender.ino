/*
	This is free and unencumbered software released into the public domain.

	Anyone is free to copy, modify, publish, use, compile, sell, or
	distribute this software, either in source code form or as a compiled
	binary, for any purpose, commercial or non-commercial, and by any
	means.

	In jurisdictions that recognize copyright laws, the author or authors
	of this software dedicate any and all copyright interest in the
	software to the public domain. We make this dedication for the benefit
	of the public at large and to the detriment of our heirs and
	successors. We intend this dedication to be an overt act of
	relinquishment in perpetuity of all present and future rights to this
	software under copyright law.

	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
	EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
	MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
	IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
	OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
	ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
	OTHER DEALINGS IN THE SOFTWARE.

	For more information, please refer to <https://unlicense.org>
*/


/*******************************************/
/*            Serial port setup            */
/*******************************************/
// Serial port speed
const uint32_t PORT_BAUD_RATE PROGMEM = 57600;


/************************************/
/*            Pins setup            */
/************************************/
// CH1 analog pin
const uint8_t CHANNEL_1_PIN PROGMEM = A0;

// CH2 analog pin
const uint8_t CHANNEL_2_PIN PROGMEM = A1;

// CH3 analog pin
const uint8_t CHANNEL_3_PIN PROGMEM = A2;

// CH4 analog pin
const uint8_t CHANNEL_4_PIN PROGMEM = A3;


/***************************************/
/*            Time settings            */
/***************************************/
// After this time in milliseconds the buffer will be pushed to the serial port
// Set to 0 to send packets immediately
const uint16_t SERIAL_PERIOD PROGMEM = 10;


// System variables
uint8_t buffer[11];
uint8_t i;
uint16_t channel_1, channel_2, channel_3, channel_4;
uint64_t serial_timer;

void setup()
{
	// Init serial port
	Serial.begin(PORT_BAUD_RATE);

	// Pre-define buffer ending
	buffer[9] = 255;
	buffer[10] = 255;
}

void loop()
{
	// Read ADC values
	read_channels();

	// Fill buffer
	fill_buffer();

	if (millis() - serial_timer > SERIAL_PERIOD) {
		// Push buffer to the serial port
		Serial.write(buffer, 11);

		// Reset timer
		serial_timer = millis();
	}
}

/// <summary>
/// Fills buffer with 4 ADC values
/// </summary>
void fill_buffer(void) {
	// Fill with channel values
	buffer[0] = channel_1 >> 8;
	buffer[1] = channel_1;
	buffer[2] = channel_2 >> 8;
	buffer[3] = channel_2;
	buffer[4] = channel_3 >> 8;
	buffer[5] = channel_3;
	buffer[6] = channel_4 >> 8;
	buffer[7] = channel_4;
	
	// Calculate checksum
	buffer[8] = 0;
	for (i = 0; i <= 7; i++)
		buffer[8] ^= buffer[i];
}

/// <summary>
/// Reads values from analog inputs
/// </summary>
void read_channels(void) {
	channel_1 = analogRead(CHANNEL_1_PIN);
	channel_2 = analogRead(CHANNEL_2_PIN);
	channel_3 = analogRead(CHANNEL_3_PIN);
	channel_4 = analogRead(CHANNEL_4_PIN);
}
