-- Sandbox for executing WikiMedia Scribunto Lua code under Python
--
-- Copyright (c) 2020-2021 Tatu Ylonen.  See file LICENSE and https://ylonen.org

-- Python function for loading a source file or Scribunto Lua module
local _python_loader = nil

env = _ENV

local loader_cache = {}

-- This function loads new a new module, whether built-in or defined in the
-- data file.
local function _new_loader(modname)
   if string.sub(modname, 1, 7) == "Module:" then
      modname = string.sub(modname, 8)
   end
   -- print("lua new_loader: " .. modname)
   if loader_cache[modname] ~= nil then
      return loader_cache[modname]
   end
   local content = nil
   if _python_loader ~= nil then
      content = _python_loader(modname)
   else
      error("PYTHON LOADER NOT SET - call lua_set_loader() first")
   end
   if content == nil then
      return nil
   end

   -- Load the content into the Lua interpreter.
   local ret = assert(load(content, modname, "t", env))
   -- XXX this seems to break things, apparently modules get initialized
   -- in wrong environments.  Temporarily disabled while fixing the real issue.
   -- loader_cache[modname] = ret
   return ret
end

-- Register the new loader as the only package searcher in Lua.
package.searchers = {}
package.searchers[0] = nil
package.searchers[1] = _new_loader

local function _lua_set_python_loader(fn)
   -- Only allow calling this function once for security reasons.
   if _python_loader ~= nil then
      error("Python loader already set")
   end
   _python_loader = fn
end

-- Maximum allowed execution time in Lua code (seconds)
local _lua_max_time = 20

-- Max time for the current call to Lua.  This is reset for every call to the
-- Lua sandbox.
local _lua_current_max_time = nil

-- Reduces Lua timeout (used only for testing).  This is exposed to the
-- sandbox and may be called from hostile code.
function _lua_set_timeout(timeout)
   if timeout ~= nil and timeout > 0.01 and timeout < _lua_max_time then
      _lua_current_max_time = timeout
   else
      _lua_current_max_time = _lua_max_time
   end
   local start_time = os.time()
   debug.sethook(function()
         if os.time() > start_time + _lua_current_max_time then
            error("Lua timeout error")
         end
                 end, "", 100000)
end

-- Wiktionary uses a Module named "string".  Force it to be loaded by
-- require() when requested (it is used in many places in Wiktionary).
package.loaded["string"] = nil

-- Wiktionary uses a Module named "debug".  Force it to be loaded by
-- require() when requested.
package.loaded["debug"] = nil

-- This debugging snippet is adapted from:
-- https://stackoverflow.com/questions/53399079/tracing-execution-of-lua-sripts
-- local level=0
-- local function hook(event)
--  local t=debug.getinfo(3)
--  io.write(level," >>> ",string.rep(" ",level))
--  if t~=nil and t.currentline>=0 then io.write(t.short_src,":",t.currentline," ") end
--  t=debug.getinfo(2)
--  if event=="call" then
--   level=level+1
--  else
--   level=level-1 if level<0 then level=0 end
--  end
--  if t.what=="main" then
--   if event=="call" then
--    io.write("begin ",t.short_src)
--   else
--    io.write("end ",t.short_src)
--   end
--  elseif t.what=="Lua" then
--   io.write(event," ",t.name or "(Lua)"," <",t.linedefined,":",t.short_src,">")
--  else
--  io.write(event," ",t.name or "(C)"," [",t.what,"] ")
--  end
--  io.write("\n")
-- end

-- Comment this out to disable debugging, uncomment to enable tracing Lua code.
-- Warning: you may need to disable max time checking by commenting out
-- its hook for this to work.
-- debug.sethook(hook,"cr")

-- Save original versions of these functions once
local _orig_format = string.format
local _orig_gsub = string.gsub
local _orig_insert = table.insert
local _orig_next = next

-- Construct a new restricted environment.  Lua modules should only be able
-- to access the functionality that is available in this restricted
-- environment.  Please report an issue on github if you find a way to
-- circumvent the environment restrictions and access outside the sandbox.
function make_env()

    -- Flushes stdin buffers.  This is mostly used to make sure debug
    -- buffers are properly output before possible crashes.  This is
    -- exposed to the sandbox.
    function _lua_io_flush()
       io.flush()
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

    -- Resets the environment to the default sandbox environment
    function _lua_reset_env(setter)
       assert(os.clock ~= nil)
       assert(package ~= nil)
       for k, v in pairs(package.loaded) do
          if k ~= "coroutine" and k ~= "math" and k ~= "io" and
             k ~= "python" and k ~= "utf8" and k ~= "os" and k ~= "package" and
             k ~= "table" and k ~= "_G" and k ~= "_sandbox_phase1" then
                package.loaded[k] = nil
          end
       end
       setter(make_env())
    end

    env = {}
    env["_G"] = env
    env["_VERSION"] = _VERSION
    env["assert"] = assert
    env["debug"] = new_debug
    env["error"] = error
    env["getmetatable"] = getmetatable  -- MODIFY
    env["ipairs"] = ipairs
    env["math"] = math
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
    env["_lua_set_python_loader"] = _lua_set_python_loader
    env["_lua_set_timeout"] = _lua_set_timeout
    env["_lua_io_flush"] = _lua_io_flush
    env["_lua_reset_env_with_setter"] = _lua_reset_env
    env["_orig_format"] = _orig_format
    env["_orig_gsub"] = _orig_gsub
    env["_orig_insert"] = _orig_insert
    env["_orig_next"] = _orig_next
    return env
end

-- Override the environment by the restricted sandbox environment
assert(io ~= nil)
local _ENV = make_env()
assert(io == nil)
assert(_G.io == nil)
assert(make_env == nil)

return _lua_set_python_loader
