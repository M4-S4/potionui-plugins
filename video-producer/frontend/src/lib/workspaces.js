export const PLAYER = 'play';

export const WORKSPACES = [
	{ id: 'media', icon: 'image', command: 'ws-media' },
	{ id: PLAYER, icon: 'play', command: 'ws-play' },
	{ id: 'director', icon: 'sparkles', command: 'ws-director' },
	{ id: 'storyboard', icon: 'grid', command: 'ws-story' },
	{ id: 'scene', icon: 'cube', command: 'ws-scene' },
	{ id: 'mixer', icon: 'sliders', command: 'ws-mixer' }
];

export const isPlayer = (workspace) => workspace === PLAYER;
