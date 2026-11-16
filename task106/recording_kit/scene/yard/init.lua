-- Scripted recording scene (not shipped): a small yard with two animated boards, a penguin that
-- walks a loop in front of them carrying a little board, and a fixed camera path.
core.send_join_message = function() end
core.send_leave_message = function() end
core.get_server_status = function() return "" end

local MP = core.get_modpath("yard")
local P = dofile(MP .. "/params.lua")
local X0, Z0 = P.x0, P.z0
local G -- ground node level, found at runtime

local function find_ground(x, z)
	for y = 60, -20, -1 do
		local n = core.get_node({x = x, y = y, z = z}).name
		local d = core.registered_nodes[n]
		if n ~= "air" and n ~= "ignore" and d and d.walkable and
				core.get_item_group(n, "tree") == 0 and core.get_item_group(n, "leaves") == 0 then
			return y
		end
	end
	return 0
end

local function build()
	G = P.ground or find_ground(X0, Z0)
	for dx = -P.r, P.r do for dz = -P.r, P.r do
		if dx * dx + dz * dz <= P.r * P.r then
			for y = G - 3, G - 1 do core.set_node({x = X0 + dx, y = y, z = Z0 + dz}, {name = "default:dirt"}) end
			core.set_node({x = X0 + dx, y = G, z = Z0 + dz}, {name = P.top})
			for y = G + 1, G + 14 do core.set_node({x = X0 + dx, y = y, z = Z0 + dz}, {name = "air"}) end
		end
	end end
	for _, f in ipairs(P.fill or {}) do
		core.set_node({x = X0 + f[1], y = G + f[2], z = Z0 + f[3]}, {name = f[4], param2 = f[5] or 0})
	end
	core.log("action", ("[scene] yard at %d,%d,%d"):format(X0, G, Z0))
end

local STRIP = {"yard_board_front.png"}

core.register_entity("yard:board_upright", {
	initial_properties = {
		visual = "upright_sprite",
		textures = {"yard_board_front.png", "yard_board_back.png"},
		spritediv = {x = 1, y = 4},
		physical = false, pointable = false, static_save = false,
	},
	on_activate = function(self)
		self.object:set_sprite({x = 0, y = 0}, 4, P.framelength, false)
	end,
})

core.register_entity("yard:board_sprite", {
	initial_properties = {
		visual = "sprite",
		textures = STRIP,
		spritediv = {x = 1, y = 4},
		physical = false, pointable = false, static_save = false,
	},
	on_activate = function(self)
		self.object:set_sprite({x = 0, y = 0}, 4, P.framelength, false)
	end,
})

core.register_entity("yard:sign", {
	initial_properties = {
		visual = "sprite",
		textures = STRIP,
		visual_size = {x = P.sign_size, y = P.sign_size},
		spritediv = {x = 1, y = 4},
		physical = false, pointable = false, static_save = false,
	},
	on_activate = function(self)
		self.object:set_sprite({x = 0, y = 0}, 4, P.framelength, false)
	end,
})

core.register_entity("yard:penguin", {
	initial_properties = {
		visual = "sprite",
		textures = {"yard_penguin.png"},
		visual_size = {x = P.penguin_size, y = P.penguin_size},
		spritediv = {x = 6, y = 2},
		automatic_face_movement_dir = 0.0,
		physical = false, pointable = false, static_save = false,
	},
	on_activate = function(self)
		self.object:set_sprite({x = 0, y = 0}, 2, 0.25, true)
	end,
})

local penguin, ready, t0, started
local function spawn()
	local y = G + 0.5
	for _, b in ipairs(P.boards) do
		local o = core.add_entity({x = X0 + b.x, y = y + b.y, z = Z0 + b.z}, b.name)
		if o and b.yaw then o:set_yaw(b.yaw) end
	end
	local c = P.loop[1]
	penguin = core.add_entity({x = X0 + c.x, y = y + P.penguin_size / 2, z = Z0 + c.z}, "yard:penguin")
	local sign = core.add_entity({x = X0 + c.x, y = y + 2, z = Z0 + c.z}, "yard:sign")
	if sign and penguin then
		sign:set_attach(penguin, "", {x = 0, y = P.sign_offset, z = 0}, {x = 0, y = 0, z = 0})
	end
end

-- penguin walks the loop's legs one after another at a constant speed
local function penguin_step(t)
	if not penguin or not penguin:get_pos() then return end
	local L = P.loop
	local total = 0
	for i = 1, #L do total = total + L[i].dur end
	local tt = t % total
	local acc = 0
	for i = 1, #L do
		local a, b = L[i], L[i % #L + 1]
		if tt < acc + a.dur then
			local v = {x = (b.x - a.x) / a.dur, y = 0, z = (b.z - a.z) / a.dur}
			local cur = penguin:get_velocity()
			if not cur or math.abs(cur.x - v.x) > 1e-3 or math.abs(cur.z - v.z) > 1e-3 then
				local s = (tt - acc) / a.dur
				penguin:set_pos({x = X0 + a.x + (b.x - a.x) * s, y = G + 0.5 + P.penguin_size / 2,
					z = Z0 + a.z + (b.z - a.z) * s})
				penguin:set_velocity(v)
			end
			return
		end
		acc = acc + a.dur
	end
end

local function lerp(a, b, s) return a + (b - a) * s end
local function key_at(t)
	local path = P.path
	local function look(pos, tg)
		local p = {x = X0 + pos.x, y = G + pos.y, z = Z0 + pos.z}
		local q = {x = X0 + tg.x, y = G + tg.y, z = Z0 + tg.z}
		local dx, dy, dz = q.x - p.x, q.y - (p.y + 1.47), q.z - p.z
		return {pos = p, yaw = math.atan2(-dx, dz), pitch = math.atan2(-dy, math.sqrt(dx * dx + dz * dz))}
	end
	if t <= path[1].t then return look(path[1].pos, path[1].target) end
	for i = 1, #path - 1 do
		local a, b = path[i], path[i + 1]
		if t <= b.t then
			local s = (t - a.t) / (b.t - a.t)
			s = s * s * (3 - 2 * s)
			local function lv(u, v) return {x = lerp(u.x, v.x, s), y = lerp(u.y, v.y, s), z = lerp(u.z, v.z, s)} end
			return look(lv(a.pos, b.pos), lv(a.target, b.target))
		end
	end
	local e = path[#path]
	return look(e.pos, e.target)
end

core.register_on_joinplayer(function(player)
	local name = player:get_player_name()
	core.set_player_privs(name, {fly = true, noclip = true, fast = true, interact = true})
	player:hud_set_flags({hotbar = false, healthbar = false, crosshair = false,
		wielditem = false, breathbar = false, minimap = false, minimap_radar = false})
	player:set_physics_override({gravity = 0, speed = 0, jump = 0})
	player:set_properties({visual_size = {x = 0, y = 0}, makes_footstep_sound = false})
	core.set_timeofday(P.time or 0.5)
	player:set_pos({x = X0, y = 40, z = Z0 - 10})
	local minp = {x = X0 - 48, y = -20, z = Z0 - 48}
	local maxp = {x = X0 + 48, y = 60, z = Z0 + 48}
	core.emerge_area(minp, maxp, function(_, _, remaining)
		if remaining == 0 then
			core.after(1.0, function()
				build()
				local fl = io.open(core.get_worldpath() .. "/scene_loaded", "w"); if fl then fl:write("1"); fl:close() end
				core.after(P.settle or 6, function()
					spawn()
					core.after(1.0, function() ready = true; t0 = core.get_us_time() end)
				end)
			end)
		end
	end)
end)

core.register_globalstep(function()
	local player = core.get_player_by_name("rec")
	if not player or not G then return end
	if not ready then
		local k = key_at(0)
		player:set_pos(k.pos); player:set_look_horizontal(k.yaw); player:set_look_vertical(k.pitch)
		return
	end
	local t = (core.get_us_time() - t0) / 1e6
	if not started then
		local f = io.open(core.get_worldpath() .. "/scene_started", "w")
		if f then f:write("1"); f:close() end
		started = true
	end
	penguin_step(t)
	local k = key_at(t)
	player:set_pos(k.pos)
	player:set_look_horizontal(k.yaw)
	player:set_look_vertical(k.pitch)
end)
