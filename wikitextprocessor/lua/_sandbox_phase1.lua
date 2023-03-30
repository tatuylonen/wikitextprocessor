-- Sandbox for executing WikiMedia Scribunto Lua code under Python
--
-- Copyright (c) 2020-2023 Tatu Ylonen.  See file LICENSE and https://ylonen.org

-- Python function for loading a source file or Scribunto Lua module
local _python_loader = nil

-- The new sandbox environment we create
local env = {}
-- for k, v in pairs(_ENV) do
--    env[k] = v
-- end
-- print("_ENV", _ENV, type(_ENV))
-- local _ENV = env
-- print("new _ENV", _ENV, type(_ENV))

local loader_cache = {}
local value_cache = {}
local _orig_package = package

-- This function loads new a new module, whether built-in or defined in the
-- data file, and returns its initialization function.  This caches the
-- initialization function.
function new_loader(modname)
   -- this module wreaks havoc on the global namespace
   if modname == "Module:No globals" then
      return nil, "Module banned"
   end
   -- print("lua new_loader: " .. modname)
   -- If the module is in the normal cache (loaded by require), call its
   -- intialization function
   if loader_cache[modname] ~= nil then
      return loader_cache[modname]
   end
   -- Otherwise load the module
   local content = nil
   if _python_loader ~= nil then
      content = _python_loader(modname)
   else
      error("PYTHON LOADER NOT SET - call lua_set_loader() first")
   end
   if content == nil then
      return nil, "module not found"
   end

   -- Load the content into the Lua interpreter.
   local fn, msg = load(content, modname, "t", env)
   -- print(tostring(fn).."  "..tostring(msg))
   -- Cache the loaded module initialization function
   loader_cache[modname] = fn
   return fn, msg
end

-- Tries to look up a module loaded by require() from the cache.  This is
-- also called from _lua_invoke().
function _cached_mod(modname)
   if _orig_package.loaded[modname] then
      return _orig_package.loaded[modname]
   end
   return nil
end

-- Saves module loaded by require() into a cache.  This is also called
-- from _lua_invoke().
function _save_mod(modname, mod)
   _orig_package.loaded[modname] = mod
end

-- Re-implements require()
function new_require(modname)
   -- If the module has already been loaded after last Lua reset, then
   -- just return the same values (even for non-data packages)
   -- print("new_require", modname)
   local mod = _cached_mod(modname)
   if mod ~= nil then
      return mod
   end
   -- Load the module and create initialization function
   local fn, msg = new_loader(modname)
   assert(fn, msg)
   assert(fn ~= true)
   local ret = fn(env)
   assert(ret)
   -- Save value in package.loaded.  Note that package.loaded is cleared
   -- whenever we reset the Lua environment.
   _save_mod(modname, ret)
   return ret
end

-- Implements mw.loadData function, which always returns the same data without
-- re-executing the initialization function.
local function new_loadData(modname)
   -- If the module is in value cache (loaded by mw.loadData), just use its
   -- value as-is
   -- print("new_loadData", modname)
   if value_cache[modname] ~= nil then
      return value_cache[modname]
   end
   -- Load the module and create initialization function
   local fn, msg = new_loader(modname)
   assert(fn, msg)
   local ret = fn(env)

   -- If caching data (for mw.loadData), save the value.  This is kept
   -- across Lua environment resets.
   value_cache[modname] = ret
   return ret
end

-- We don't use the default require. Disable its paths too.
package.searchers = {}
package.searchers[0] = nil
package.searchers[1] = nil

-- Wiktionary uses a Module named "string".  Force it to be loaded by
-- require() when requested (it is used in many places in Wiktionary).
package.loaded["string"] = nil

local function _lua_set_python_loader(fn)
   -- Only allow calling this function once for security reasons.
   if _python_loader ~= nil then
      error("Python loader already set")
   end
   _python_loader = fn
end

-- Maximum allowed execution time in Lua code (seconds)
local _lua_max_time = 60

-- Max time for the current call to Lua.  This is reset for every call to the
-- Lua sandbox.
local _lua_current_max_time = nil

-- Reduces Lua timeout (used only for testing).  This is exposed to the
-- sandbox and may be called from hostile code.
local function _lua_set_timeout(timeout)
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
local _orig_tostring = tostring

local _orig_VERSION = _VERSION
local _orig_assert = assert
local _orig_debug = new_debug
local _orig_error = error
local _orig_getmetatable = getmetatable
local _orig_ipairs = ipairs
local _orig_math = math
local _orig_pairs = pairs
local _orig_pcall = pcall
local _orig_print = print
local _orig_rawequal = rawequal
local _orig_rawget = rawget
local _orig_rawset = rawset
local _orig_select = select
local _orig_setmetatable = setmetatable
local _orig_string = string
local _orig_table = table
local _orig_tonumber = tonumber
local _orig_tostring = tostring
local _orig_type = type
local _orig_unpack = unpack
local _orig_xpcall = xpcall
local _orig_new_require = new_require

local retained_modules = {
   coroutine = true,
   math = true,
   io = true,
   python = true,
   utf8 = true,
   os = true,
   package = true,
   table = true,
   _G = true,
   _sandbox_phase1 = true,
   -- We also keep some very frequently used modules that we know can be
   -- reused for other calls and pages
   string = true,
   mw = true, -- needs special handling due to global "mw" in _lua_reset_env()
   mw_hash = true,
   mw_html = true,
   mw_language = true,
   mw_site = true,
   mw_text = true,
   mw_title = true,
   mw_uri = true,
};

retained_modules["ustring:ustring"] = true
retained_modules["ustring/lower"] = true
retained_modules["ustring/upper"] = true
retained_modules["ustring/charsets"] = true
retained_modules["ustring/normalization-data"] = true
retained_modules["libraryUtil"] = true
-- Some Wiktionary modules that we know to be safe.  These really should
-- come from elsewhere.  These are loaded very frequently, so keeping them
-- cached speeds up things.
local module_namespace_name = NAMESPACE_DATA.Module.name
retained_modules[module_namespace_name .. ":languages"] = true
retained_modules[module_namespace_name .. ":languages/templates"] = true
retained_modules[module_namespace_name .. ":language-like"] = true
retained_modules[module_namespace_name .. ":wikimedia languages"] = true
retained_modules[module_namespace_name .. ":families"] = true
retained_modules[module_namespace_name .. ":scripts"] = true
retained_modules[module_namespace_name .. ":links"] = true
retained_modules[module_namespace_name .. ":links/templates"] = true
retained_modules[module_namespace_name .. ":utilities"] = true
retained_modules[module_namespace_name .. ":utils"] = true
retained_modules[module_namespace_name .. ":debug"] = true
retained_modules[module_namespace_name .. ":palindromes"] = true
retained_modules[module_namespace_name .. ":table"] = true
retained_modules[module_namespace_name .. ":IPA"] = true
retained_modules[module_namespace_name .. ":IPA/templates"] = true
retained_modules[module_namespace_name .. ":IPA/tracking"] = true
retained_modules[module_namespace_name .. ":script utilities"] = true
retained_modules[module_namespace_name .. ":string"] = true
retained_modules[module_namespace_name .. ":string utilities"] = true
retained_modules[module_namespace_name .. ":syllables"] = true
retained_modules[module_namespace_name .. ":parameters"] = true
retained_modules[module_namespace_name .. ":translations"] = true
retained_modules[module_namespace_name .. ":gender and number"] = true
retained_modules[module_namespace_name .. ":qualifier"] = true
retained_modules[module_namespace_name .. ":accent qualifier"] = true
retained_modules[module_namespace_name .. ":ugly hacks"] = true
retained_modules[module_namespace_name .. ":redlink category"] = true
retained_modules[module_namespace_name .. ":etymology"] = true
retained_modules[module_namespace_name .. ":etymology/templates"] = true
retained_modules[module_namespace_name .. ":italics"] = true
retained_modules[module_namespace_name .. ":usex"] = true
retained_modules[module_namespace_name .. ":usex/templates"] = true
retained_modules[module_namespace_name .. ":number-utilities"] = true
retained_modules[module_namespace_name .. ":check isxn"] = true
retained_modules[module_namespace_name .. ":rhymes"] = true
retained_modules[module_namespace_name .. ":labels"] = true
retained_modules[module_namespace_name .. ":TemplateStyles"] = true
retained_modules[module_namespace_name .. ":columns"] = true
retained_modules[module_namespace_name .. ":collation"] = true
retained_modules[module_namespace_name .. ":glossary"] = true

-- Note: the following are examples that cannot be retained:
--   Module:headword (saves page title)
--   Module:time ??? (uses mw.getContentLanguage() - is this page-dependent?)
--   Module:quote (uses Module:time)
--   Module:form of (form_of/functions table display_handlers is suspicious)

-- Construct a new restricted environment.  Lua modules should only be able
-- to access the functionality that is available in this restricted
-- environment.  Please report an issue on github if you find a way to
-- circumvent the environment restrictions and access outside the sandbox.
local function _lua_reset_env()

    -- Clear some metatables
    setmetatable(_G, nil)

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

    -- Cause most packages to be reloaded
    for k, v in pairs(package.loaded) do
       if retained_modules[k] == nil then
          package.loaded[k] = nil
       end
    end

    -- Clear the sandbox environment, except the "mw" global.  Not clearing it
    -- enables us to cache the module, which provides some speedup.
    -- "next" function is (re)defined in _sandbox_phase2.lua and we keep it too.
    -- also keep the namespace texts
    for k, v in pairs(env) do
       if k ~= "mw" and k ~= "next" and k ~= "NAMESPACE_DATA" then
          env[k] = nil
       end
    end

    -- Set only a few desired values in the sandbox environment
    assert(_VERSION ~= nil)
    env["_G"] = env
    env["_VERSION"] = _orig_VERSION
    env["assert"] = _orig_assert
    env["debug"] = new_debug
    env["error"] = _orig_error
    env["getmetatable"] = _orig_getmetatable
    env["ipairs"] = _orig_ipairs
    env["math"] = _orig_math
    env["_orig_next"] = _orig_next
    env["os"] = new_os
    env["pairs"] = _orig_pairs
    env["_orig_pairs"] = _orig_pairs
    env["pcall"] = _orig_pcall
    env["print"] = _orig_print
    env["rawequal"] = _orig_rawequal
    env["rawget"] = _orig_rawget
    env["rawset"] = _orig_rawset
    env["require"] = _orig_new_require
    env["select"] = _orig_select
    env["setmetatable"] = _orig_setmetatable
    env["string"] = _orig_string
    env["table"] = _orig_table
    env["tonumber"] = _orig_tonumber
    env["tostring"] = _orig_tostring
    env["type"] = _orig_type
    env["unpack"] = unpack
    env["xpcall"] = _orig_xpcall
    env["_lua_set_python_loader"] = _lua_set_python_loader
    env["_lua_set_timeout"] = _lua_set_timeout
    env["_lua_io_flush"] = _lua_io_flush
    env["_lua_reset_env"] = _lua_reset_env
    env["_orig_format"] = _orig_format
    env["_orig_gsub"] = _orig_gsub
    env["_orig_tostring"] = _orig_tostring
    env["_orig_next"] = _orig_next
    env["_orig_insert"] = _orig_insert
    env["_new_loadData"] = new_loadData
    env["_new_loader"] = new_loader
    env["_cached_mod"] = _cached_mod
    env["_save_mod"] = _save_mod
    -- namespace
    env["NAMESPACE_DATA"] = NAMESPACE_DATA
    return env
end

-- Switch to the sandbox environment
assert(io ~= nil)  -- We should not be in the sandbox now
_lua_reset_env()
-- call it a couple more times to ensure it still works
_lua_reset_env()
_lua_reset_env()
-- Now we should be in the sandbox environment

return _lua_set_python_loader
