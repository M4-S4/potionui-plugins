export const PLAYER = 'play';

export const WORKSPACES = [
	{ id: 'media', icon: 'image', command: 'ws-media' },
	{ id: 'storyboard', icon: 'grid', command: 'ws-story' },
	{ id: 'director', icon: 'sparkles', command: 'ws-director' },
	{ id: 'mixer', icon: 'sliders', command: 'ws-mixer' },
	{ id: PLAYER, icon: 'play', command: 'ws-play' }
];

export const isPlayer = (workspace) => workspace === PLAYER;
