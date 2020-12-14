-- Sandbox for executing WikiMedia Scribunto Lua code under Python
--
-- Copyright (c) 2020 Tatu Ylonen.  See file LICENSE and https://ylonen.org

local env = _ENV

mw = nil  -- assigned in lua_set_loader()
python_loader = nil

-- Maximum allowed execution time in Lua code (seconds)
lua_max_time = 20

-- Max time for the current call to Lua.  This is reset for every call to the
-- Lua sandbox.
lua_current_max_time = nil

-- This function loads new a new module, whether built-in or defined in the
-- data file.
function new_loader(modname)
   --print("lua new_loader: " .. modname)
   local content = nil
   if python_loader ~= nil then
      content = python_loader(modname)
   else
      error("PYTHON LOADER NOT SET - call lua_set_loader() first")
   end
   if content == nil then
      return nil
   end

   -- Wikimedia uses an older version of Lua.  Make certain substitutions
   -- to make existing code run on more modern versions of Lua.
   content = string.gsub(content, "\\\\", "\\092")
   content = string.gsub(content, "%%\\%[", "%%%%[")
   content = string.gsub(content, "\\:", ":")
   content = string.gsub(content, "\\,", ",")
   content = string.gsub(content, "\\%(", "%%(")
   content = string.gsub(content, "\\%)", "%%)")
   content = string.gsub(content, "\\%+", "%%+")
   content = string.gsub(content, "\\%*", "%%*")
   content = string.gsub(content, "\\>", ">")
   content = string.gsub(content, "\\%.", "%%.")
   content = string.gsub(content, "\\%?", "%%?")
   content = string.gsub(content, "\\%-", "%%-")
   content = string.gsub(content, "\\!", "!")
   content = string.gsub(content, "\\|", "|")  -- XXX tentative, see ryu:951
   content = string.gsub(content, "\\ʺ", "ʺ")

   -- Load the content into the Lua interpreter.
   local ret = assert(load(content, modname, "bt", env))
   return ret
end

-- Register the new loader as the only package searcher in Lua.
package.searchers = {}
package.searchers[0] = nil
package.searchers[1] = new_loader

-- This should be called immediately after loading the sandbox to set the
-- Python function that will be used for loading Lua modules and various
-- other Python functions that implement some of the functionality needed
-- for executing Scribunto code (these functions are called from Lua code).
function lua_set_loader(loader, mw_text_decode, mw_text_encode,
                        mw_text_jsonencode, mw_text_jsondecode,
                        get_page_info, get_page_content, fetch_language_name,
                        fetch_language_names)
   python_loader = loader
   mw = require("mw")
   mw.text.decode = mw_text_decode
   mw.text.encode = mw_text_encode
   mw.text.jsonEncode = mw_text_jsonencode
   mw.text.jsonDecode = mw_text_jsondecode
   mw.title.python_get_page_info = get_page_info
   mw.title.python_get_page_content = get_page_content
   mw.language.python_fetch_language_name = fetch_language_name
   mw.language.python_fetch_language_names = fetch_language_names
end

function frame_args_index(new_args, key)
   -- print("frame_args_index", key)
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

function frame_args_pairs(new_args)
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

function frame_args_ipairs(new_args)
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

function frame_args_len(new_args)
   return #new_args._orig
end

function frame_args_next(t, key)
   if key == nil then key = "***nil***" end
   local nkey = t._next_key[key]
   if nkey == nil then return nil end
   local v = t[nkey]
   if v == nil then return nil end
   return nkey, v
end

frame_args_meta = {
   __index = frame_args_index,
   __pairs = frame_args_pairs,
   __next = frame_args_next,
   __len = frame_args_len
}

function frame_new_child(frame, o)
   local title = (o and o.title) or ""
   local args = (o and o.args) or {}
   local new_frame = mw.clone(frame)
   new_frame.getParent = function() return frame end
   new_frame.getTitle = function() return title end
   new_frame.args = args
   prepare_frame_args(new_frame)
   return new_frame
end

function prepare_frame_args(frame)
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
  frame.getArgument = frame_get_argument
  frame.newChild = frame_new_child
end

function frame_get_argument(frame, name)
   if type(name) == "table" then name = name.name end
   v = frame.args[name]
   if v == nil then return nil end
   return { expand = function() return v end }
end

-- This function implements the {{#invoke:...}} parser function.
-- XXX need better handling of parent frame and frame
-- This returns (true, value) if successful, (false, error) if exception.
function lua_invoke(mod_name, fn_name, frame, page_title)
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
   io.flush()
   -- Convert frame.args into a metatable that preprocesses the values
   prepare_frame_args(frame)
   -- Implement some additional functions for frame
   if pframe ~= nil then
      prepare_frame_args(pframe)
   end

   -- Initialize some fields that will be referenced from functions
   mw._frame = frame
   mw._pageTitle = page_title

   -- Set time limit for execution of the Lua code
   local start_time = os.time()
   lua_current_max_time = lua_max_time
   debug.sethook(function()
         if os.time() > start_time + lua_current_max_time then
            error("Lua timeout error")
         end
                 end, "", 100000)

   -- Load the module.  Note that the initilizations above must be done before
   -- loading the module, as the module could refer to, e.g., page title
   -- during loading.
   local success
   local mod
   success, mod = xpcall(function() return require(mod_name) end,
      debug.traceback)
   if not success then
      return False, ("\tLoading module failed in #invoke: " ..
                        mod_name .. "\n" .. mod)
   end
   -- Look up the target function in the module
   local fn = mod[fn_name]
   if fn == nil then
      return false, "\tNo function '" .. fn_name .. "' in module " .. mod_name
   end
   -- Call the function in the module
   local st, v = xpcall(function() return fn(frame) end, debug.traceback)
   -- print("Lua sandbox:", tostring(v))
   return st, v
end

-- Sets maximum lua execution time for the current call to t seconds.  The
-- value can only be lowered.  This intended for tests only.
function lua_reduce_timeout(t)
   if t < lua_current_max_time then
      lua_current_max_time = t
   else
      error("maximum execution time can only be lowered")
   end
end

-- math.log10 seems to be sometimes missing???
function math.log10(x)
   return math.log(x, 10)
end

-- Limit access to traceback in the debug module
local new_debug = { traceback = debug.traceback }

-- Limit access to a few safe functions in the os module
local new_os = {
   clock = os.clock,
   date = os.date,
   difftime = os.difftime,
   time = os.time,
}

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
local orig_format = string.format
function string.format(fmt, ...)
   local args = {...}
   local new_args = {}
   local i = 1
   for m in string.gmatch(fmt, "%%[-# +'0-9.]*([cdEefgGiouXxqs%%])") do
      if m ~= "%" then
         local arg = args[i]
         i = i + 1
         if (m == "d" or m == "i" or m == "o" or m == "u" or m == "x" or
             m == "X" or m == "c") then
            arg = math.floor(arg + 0.5)
         end
         table.insert(new_args, arg)
      end
   end
   if i < #args then
      print("Warning: extra arguments to string.format")
   end
   return orig_format(fmt, table.unpack(new_args))
end

-- Original gsub does not accept "%]" in replacement string in modern Lua,
-- while apparently some older versions did.  This is used in Wiktionary.
-- Thus we mungle the replacement string accordingly.
local orig_gsub = string.gsub
function string.gsub(text, pattern, repl)
   --print(string.format("string.gsub %q %q %q", text, pattern, tostring(repl)))
   if type(repl) == "string" then
      repl = orig_gsub(repl, "%%]", "]")
   end
   return orig_gsub(text, pattern, repl)
end

-- Original table.insert in Lua 5.1 allows inserting beyond the end of the
-- table.  Lua 5.3 does not.  Implement the old functionality for compatibility;
-- Wiktionary relies on it.  Also, it seems Wiktionary calls insert with
-- only one argument (or the second argument nil).  Ignore those calls.
local orig_insert = table.insert
function table.insert(...)
   local args = {...}
   if #args < 2 then return end
   if #args < 3 then
      orig_insert(table.unpack(args))
   else
      local pos = args[2]
      if pos > #args[1] + 1 then
         args[1][pos] = args[2]
      else
         orig_insert(table.unpack(args))
      end
   end
end

-- Change next() to use a new metamethod __next so that we can redefine it for
-- certain tables
local orig_next = next
function next(t, k)
   local m = getmetatable(t)
   local n = m and m.__next or orig_next
   return n(t, k)
end

-- This debugging snippet is adapted from:
-- https://stackoverflow.com/questions/53399079/tracing-execution-of-lua-sripts
local level=0
local function hook(event)
 local t=debug.getinfo(3)
 io.write(level," >>> ",string.rep(" ",level))
 if t~=nil and t.currentline>=0 then io.write(t.short_src,":",t.currentline," ") end
 t=debug.getinfo(2)
 if event=="call" then
  level=level+1
 else
  level=level-1 if level<0 then level=0 end
 end
 if t.what=="main" then
  if event=="call" then
   io.write("begin ",t.short_src)
  else
   io.write("end ",t.short_src)
  end
 elseif t.what=="Lua" then
  io.write(event," ",t.name or "(Lua)"," <",t.linedefined,":",t.short_src,">")
 else
 io.write(event," ",t.name or "(C)"," [",t.what,"] ")
 end
 io.write("\n")
end

-- Comment this out to disable debugging, uncomment to enable tracing Lua code.
-- Warning: you may need to disable max time checking by commenting out
-- its hook for this to work.
-- debug.sethook(hook,"cr")

-- Wiktionary uses a Module named "string".  Force it to be loaded by
-- require() when requested (it is used in many places in Wiktionary).
package.loaded["string"] = nil

-- Wiktionary uses a Module named "debug".  Force it to be loaded by
-- require() when requested.
package.loaded["debug"] = nil

-- Construct a new restricted environment.  Lua modules should only be able
-- to access the functionality that is available in this restricted
-- environment.  Please report an issue on github if you find a way to
-- circumvent the environment restrictions and access outside the sandbox.
env = {}
env["_G"] = env
env["_VERSION"] = _VERSION
env["assert"] = assert
env["debug"] = new_debug
env["error"] = error
env["getmetatable"] = getmetatable  -- MODIFY
env["ipairs"] = ipairs
env["lua_invoke"] = lua_invoke
env["lua_set_loader"] = lua_set_loader
env["math"] = math
env["mw"] = mw
env["next"] = next
env["os"] = new_os
env["pairs"] = pairs
env["pcall"] = pcall
env["print"] = print
env["rawequal"] = rawequal
env["rawget"] = rawget
env["rawset"] = rawset
env["require"] = require
env["select"] = select
env["setmetatable"] = setmetatable
env["string"] = string
env["table"] = table
env["tonumber"] = tonumber
env["tostring"] = tostring
env["type"] = type
env["unpack"] = table.unpack
env["xpcall"] = xpcall   -- MODIFY
env["lua_reduce_timeout"] = lua_reduce_timeout

-- Start using the new environment we just constructed.
local _ENV = env

-- XXX missing built-in modules?
    -- bit32
    -- libraryUtil
    -- luabit
