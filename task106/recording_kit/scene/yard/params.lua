-- Layout and camera path of the recording scene. Coordinates are relative to the yard centre
-- (x0, ground node level, z0); camera/target y is relative to the ground node level.
local P = {
	x0 = 61, z0 = -3, r = 10,
	top = "default:dirt_with_grass",
	time = 0.5,
	settle = 6,
	framelength = 1.0,
	penguin_size = 1.2,
	sign_size = 0.45,
	sign_offset = 10,
}

P.boards = {
	{name = "yard:board_upright", x = -1.5, y = 1.4, z = 4, yaw = math.pi},
	{name = "yard:board_sprite", x = 1.5, y = 1.4, z = 4},
}

P.loop = {
	{x = -2.5, z = 1.0, dur = 5},
	{x = 2.5, z = 1.0, dur = 2},
	{x = 2.5, z = -1.0, dur = 5},
	{x = -2.5, z = -1.0, dur = 2},
}

P.path = {
	{t = 0, pos = {x = 0, y = 0.5, z = -10}, target = {x = 0, y = 2.0, z = 4}},
	{t = 3, pos = {x = 0, y = 0.5, z = -5.5}, target = {x = 0, y = 1.6, z = 3}},
	{t = 15, pos = {x = 0, y = 0.5, z = -5.5}, target = {x = 0, y = 1.6, z = 3}},
	{t = 19, pos = {x = -5.5, y = 0.5, z = 2.5}, target = {x = -1.5, y = 1.8, z = 4}},
	{t = 23, pos = {x = -1.8, y = 0.5, z = 8.5}, target = {x = -0.5, y = 1.6, z = 3}},
	{t = 32, pos = {x = -1.8, y = 0.5, z = 8.5}, target = {x = -0.5, y = 1.6, z = 3}},
}

return P
