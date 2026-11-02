import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_FPS, frameDuration, wheelZoomFactor } from './timebase.js';

const near = (actual, expected, epsilon = 1e-9) => assert.ok(Math.abs(actual - expected) < epsilon, `${actual} is not ${expected}`);

test('frameDuration: one frame of the project, 25 fps when the rate is unknown', () => {
	near(frameDuration(25), 0.04);
	near(frameDuration(24), 1 / 24);
	near(frameDuration(30), 1 / 30);
	near(frameDuration('30'), 1 / 30);
	for (const bad of [0, -5, null, undefined, NaN, 'x', Infinity]) near(frameDuration(bad), 1 / DEFAULT_FPS);
});

test('wheelZoomFactor: a mouse notch zooms by 1.15 as before, a trackpad pinch by a small proportional step', () => {
	near(wheelZoomFactor({ deltaY: -100, deltaMode: 0 }), 1.15);
	near(wheelZoomFactor({ deltaY: 100, deltaMode: 0 }), 1 / 1.15);
	near(wheelZoomFactor({ deltaY: -3, deltaMode: 1 }), 1.15, 0.005);
	const pinch = wheelZoomFactor({ deltaY: -2, deltaMode: 0 });
	assert.ok(pinch > 1 && pinch < 1.01, `a pinch event of 2 px zoomed by ${pinch}`);
	near(wheelZoomFactor({ deltaY: -2, deltaMode: 0 }) * wheelZoomFactor({ deltaY: 2, deltaMode: 0 }), 1);
	let zoom = 1;
	for (let i = 0; i < 30; i++) zoom *= wheelZoomFactor({ deltaY: -3, deltaMode: 0 });
	assert.ok(zoom > 1.1 && zoom < 1.5, `thirty small events zoomed by ${zoom}`);
});

test('wheelZoomFactor: nothing for a zero or invalid delta, bounded for a huge one', () => {
	near(wheelZoomFactor({ deltaY: 0, deltaMode: 0 }), 1);
	near(wheelZoomFactor({ deltaY: NaN, deltaMode: 0 }), 1);
	near(wheelZoomFactor({ deltaMode: 0 }), 1);
	near(wheelZoomFactor({ deltaY: -100000, deltaMode: 0 }), 1.15 ** 3);
	near(wheelZoomFactor({ deltaY: 100000, deltaMode: 0 }), 1.15 ** -3);
	near(wheelZoomFactor({ deltaY: -5, deltaMode: 2 }), 1.15 ** 3);
});
