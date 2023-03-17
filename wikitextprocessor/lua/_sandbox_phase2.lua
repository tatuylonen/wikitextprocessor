-- Second phase of sandbox for executint WikiMedia Scribunto Lua code under
-- Python
--
-- Copyright (c) 2020-2022 Tatu Ylonen.  See file LICENSE and https://ylonen.org

-- Sanity check - ensure that sandbox is working
assert(new_require == nil)
assert(io == nil)
assert(_new_loadData ~= nil)

-- The main MediaWiki namespace for accessing its functions.  This is
-- created in _lua_set_functions.
mw = nil

mw_decode_python = nil
mw_encode_python = nil
mw_jsonencode_python = nil
mw_jsondecode_python = nil
mw_python_get_page_info = nil
mw_python_get_page_content = nil
mw_python_fetch_language_name = nil
mw_python_fetch_language_names = nil

-- These are used for passing information about the current call to
-- _lua_invoke().  The values are restred on return, as calls can be
-- recursive.
_mw_frame = "<unassigned>"
_mw_pageTitle = "<unassigned>"

local function frame_args_index(new_args, key)
   -- print("frame_args_index", key)
   local i = tonumber(key)
   if i ~= nil then
      key = i
   end
   local v = new_args._orig[key]
   if v == nil then return nil end
   if not new_args._preprocessed[key] then
      local frame = new_args._frame
      v = frame:preprocess(v)
      -- Cache preprocessed value so we only preprocess each argument once
      new_args._preprocessed[key] = true
      new_args._orig[key] = v
   end
   -- print("frame_args_index", key, "->", v)
   return v
end

local function frame_args_pairs(new_args)
   -- print("frame_args_pairs")
   local frame = new_args._frame
   local function stateless_iter(new_args, key)
      -- print("stateless_iter: " .. tostring(key))
      if key == nil then key = "***nil***" end
      local nkey = new_args._next_key[key]
      if nkey == nil then return nil end
      local v = new_args[nkey]
      if v == nil then return nil end
      -- print("stateless_iter returning: " .. tostring(nkey) .. "=" ..
      --          tostring(v))
      return nkey, v
   end
   return stateless_iter, new_args, nil
end

local function frame_args_ipairs(new_args)
   -- print("frame_args_ipairs")
   local frame = new_args._frame
   local function stateless_iter(new_args, key)
      -- print("ipairs stateless_iter: " .. tostring(key))
      if key == nil then key = 1 else key = key + 1 end
      local v = new_args[key]
      if v == nil then return nil end
      -- print("stateless_iter returning: " .. tostring(key) .. "=" ..
      --       tostring(v))
      return key, v
   end
   return stateless_iter, new_args, nil
end

local function frame_args_len(new_args)
   return #new_args._orig
end

local function frame_args_next(t, key)
   if key == nil then key = "***nil***" end
   local nkey = t._next_key[key]
   if nkey == nil then return nil end
   local v = t[nkey]
   if v == nil then return nil end
   return nkey, v
end

local frame_args_meta = {
   __index = frame_args_index,
   __pairs = frame_args_pairs,
   __next = frame_args_next,
   __len = frame_args_len
}

local function prepare_frame_args(frame)
  local next_key = {}
  local prev = "***nil***"
  for k, v in pairs(frame.args) do
     -- print("prepare_frame_args: k=" .. tostring(k) .. " v=" .. tostring(v))
     next_key[prev] = k
     prev = k
  end
  new_args = {_orig = frame.args, _frame = frame, _next_key = next_key,
              _preprocessed = {}}
  setmetatable(new_args, frame_args_meta)
  frame.args = new_args
  frame.argumentPairs = function (frame) return pairs(frame.args) end
  frame.getArgument = function(frame, name)
    if type(name) == "table" then name = name.name end
    v = frame.args[name]
    if v == nil then return nil end
    return { expand = function() return v end }
  end
  frame.newChild = function(frame, o)
    local title = (o and o.title) or ""
    local args = (o and o.args) or {}
    local new_frame = mw.clone(frame)
    new_frame.getParent = function() return frame end
    new_frame.getTitle = function() return title end
    new_frame.args = args
    prepare_frame_args(new_frame)
    return new_frame
  end;
end

-- This function implements the {{#invoke:...}} parser function.  XXX
-- need better handling of parent frame and frame This returns (true,
-- value) if successful, (false, error) if exception.  NOTE: This can
-- be called from hostile code, but this is defined within the
-- sandbox, so the main risks come from the argument data structures
-- in calls from Python.  Python code must keep in mind that those
-- arguments and any functions and data structures in them can be
-- accessed, called, and modified by hostile code.
local function _lua_invoke(mod_name, fn_name, frame, page_title, timeout)
   -- Initialize frame and parent frame
   local pframe = frame:getParent()
   -- print("lua_invoke", mod_name, fn_name)
   -- for k, v in pairs(frame.args) do
   --    print("", k, type(k), v, type(v))
   -- end
   -- if pframe ~= nil then
   --    print("parent")
   --    for k, v in pairs(pframe.args) do
   --       print("", k, type(k), v, type(v))
   --    end
   -- end
   _lua_io_flush()
   -- Convert frame.args into a metatable that preprocesses the values
   prepare_frame_args(frame)
   -- Implement some additional functions for frame
   if pframe ~= nil then
      prepare_frame_args(pframe)
   end

   -- Initialize some fields that will be referenced from functions
   local saved_frame = _mw_frame
   local saved_pageTitle = _mw_pageTitle
   _mw_frame = frame
   _mw_pageTitle = page_title

   -- Set time limit for execution of the Lua code
   _lua_set_timeout(timeout)

   -- Load the module.  Note that the initilizations above must be done before
   -- loading the module, as the module could refer to, e.g., page title
   -- during loading.
   local mod, success
   local module_ns_name = NAMESPACE_DATA.Module.name
   if string.sub(mod_name, 1, #module_ns_name + 1) ~= module_ns_name .. ":" then
      local mod1 = module_ns_name .. ":" .. mod_name
      mod = _cached_mod(mod1)
      if not mod then
         local initfn, msg = _new_loader(mod1)
         if initfn then
            success, mod = xpcall(initfn, debug.traceback, _G)
            if not success then
               _mw_frame = saved_frame
               _mw_pageTitle = saved_pageTitle
               return false, ("\tLoading module failed in #invoke: " ..
                                 mod1 .. "\n" .. mod)
            end
            _save_mod(mod1, mod)
         end
      end
   end
   if not mod then
      mod = _cached_mod(mod_name)
      if not mod then
         local initfn, msg = _new_loader(mod_name)
         if initfn then
            success, mod = xpcall(initfn, debug.traceback, _G)
            if not success then
               _mw_frame = saved_frame
               _mw_pageTitle = saved_pageTitle
               return false, ("\tLoading module failed in #invoke: " ..
                                 mod_name .. "\n" .. mod)
            end
            _save_mod(mod_name, mod)
         else
            error("Could not find module " .. mod_name .. ": " .. msg)
         end
      end
   end
   assert(mod)
   -- Look up the target function in the module
   local fn = mod[fn_name]
   if fn == nil then
      _mw_frame = saved_frame
      _mw_pageTitle = saved_pageTitle
      return false, "\tNo function '" .. fn_name .. "' in module " .. mod_name
   end
   -- Call the function in the module
   local st, v = xpcall(fn, debug.traceback, frame)
   -- print("Lua sandbox:", tostring(v))
   _mw_frame = saved_frame
   _mw_pageTitle = saved_pageTitle
   return st, v
end

-- This should be called immediately after loading the sandbox to set the
-- Python function that will be used for loading Lua modules and various
-- other Python functions that implement some of the functionality needed
-- for executing Scribunto code (these functions are called from Lua code).
local function _lua_set_functions(mw_text_decode, mw_text_encode,
                                  mw_text_jsonencode, mw_text_jsondecode,
                                  get_page_info, get_page_content,
                                  fetch_language_name, fetch_language_names)
   -- Note: this is exposed to the Lua sandbox and the Lua sandbox can access
   -- the functions via mw.  Thus all the Python functions provided here
   -- must be safe to call from hostile code.
   mw = require("mw")
   mw_decode_python = mw_text_decode
   mw_encode_python = mw_text_encode
   mw_jsonencode_python = mw_text_jsonencode
   mw_jsondecode_python = mw_text_jsondecode
   mw_python_get_page_info = get_page_info
   mw_python_get_page_content = get_page_content
   mw_python_fetch_language_name = fetch_language_name
   mw_python_fetch_language_names = fetch_language_names
end

-- math.log10 seems to be sometimes missing???
function math.log10(x)
   return math.log(x, 10)
end

-- This is a compatibility function for an older version of Lua (the getn
-- function was deprecated and then removed, but it is used in Wiktionary)
function table.getn(tbl)
   return #tbl
end

-- This is a compatibility function for an older version of Lua.  Apparently
-- the math.mod function was renamed to math.fmod in Lua 5.1.
function math.mod(a, b)
   return math.fmod(a, b)
end

-- With the introduction of 64-bit integer type in Lua 5.3, the %d and similar
-- formats in string.format no longer accept floating point arguments.  Remedy
-- that by expressly converting arguments to such formatting codes into
-- integers.
function string.format(fmt, ...)
   -- local arg = {...}
   local new_args = {}
   local i = 1
   for m in string.gmatch(fmt, "%%[-# +'0-9.]*([cdEefgGiouXxqs%%])") do
      if m ~= "%" then
         local ar = arg[i]
         i = i + 1
         if (m == "d" or m == "i" or m == "o" or m == "u" or m == "x" or
             m == "X" or m == "c") then
            ar = math.floor(ar + 0.5)
         end
         table.insert(new_args, ar)
      end
   end
   if i < #arg then
      print("Warning: extra arguments to string.format")
   end
   return _orig_format(fmt, table.unpack(new_args))
end

-- Original gsub does not accept "%]" in replacement string in modern Lua,
-- while apparently some older versions did.  This is used in Wiktionary.
-- Thus we mungle the replacement string accordingly.
function string.gsub(text, pattern, repl)
   -- print(string.format("string.gsub %q %q %q", text, pattern, tostring(repl)))
   if type(repl) == "string" then
      -- First replace all escaped magical character ("%.", "%["), unless
      -- they are immediately preceded by an escaped % ("%%" so ("%%%%")
      repl = _orig_gsub(repl, "([^%%])%%([%$%(%)%.%[%]%*%+%?%^])", "%1%2")
      -- Round 2 is needed when patterns overlap like with "%)%.":
      -- because the parenthese is the `([^%%])` of the `%.` match,
      -- the cursor of the pattern engine continues from there and misses
      -- the latter.
      repl = _orig_gsub(repl, "%%%%", "__PERC__")
      repl = _orig_gsub(repl, "%%([%$%(%)%.%[%]%*%+%?%^])", "%1")
      -- Handle - separately, this is left from the old code.
      if pattern ~= "%-" or repl ~= "%%-" then
         repl = _orig_gsub(repl, "%%%-", "-")
      end
      repl = _orig_gsub(repl, "__PERC__", "%%%%")
   end
   return _orig_gsub(text, pattern, repl)
end

-- Original table.insert in Lua 5.1 allows inserting beyond the end of the
-- table.  Lua 5.3 does not.  Implement the old functionality for compatibility;
-- Wiktionary relies on it.  Also, it seems Wiktionary calls insert with
-- only one argument (or the second argument nil).  Ignore those calls.
function table.insert(...)
   local args = {...}
   if #args < 2 then return end
   if #args < 3 then
      _orig_insert(table.unpack(args))
   else
      local pos = args[2]
      if pos > #args[1] + 1 then
         args[1][pos] = args[2]
      else
         _orig_insert(table.unpack(args))
      end
   end
end

-- Change next() to use a new metamethod __next so that we can redefine it for
-- certain tables
function next(t, k)
   local m = getmetatable(t)
   local n = m and m.__next or _orig_next
   return n(t, k)
end

-- Lua 5.2 tostring(60/20)=="3", Lua 5.3.3 tostring(60/20)=="3.0"
function tostring(v)
   if type(v) == "number" and math.abs(v) > 0.5 and
      math.abs(v - math.floor(v + 0.5)) < 0.000001 then
      return string.format("%.0f", v)
   end
   return _orig_tostring(v)
end

-- XXX missing built-in modules?
    -- bit32
    -- libraryUtil
    -- luabit

-- Make sure we are operating in the restricted environment
assert(io == nil)
assert(_G.io == nil)

return { _lua_set_functions, _lua_invoke, _lua_reset_env }
