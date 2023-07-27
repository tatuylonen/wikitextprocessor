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
mw_wikibase_getlabel_python = nil
mw_wikibase_getdesc_python = nil

-- These are used for passing information about the current call to
-- _lua_invoke().  The values are restred on return, as calls can be
-- recursive.
_mw_frame = "<unassigned>"
_mw_pageTitle = "<unassigned>"

local function frame_args_index(new_args, key)
   -- print("frame_args_index", key)
   local i = tonumber(key)
   if key ~= "inf" and key ~= "nan" and i ~= nil then
      key = i
   end
   local v = new_args._orig[key]
   if v == nil then
       return nil
   end
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
   __next = frame_args_next,
}

local function prepare_frame_args(frame)
  local next_key = {}
  local prev = "***nil***"
  for k, v in pairs(frame.args) do
     -- print("prepare_frame_args: k=" .. tostring(k) .. " v=" .. tostring(v))
     next_key[prev] = k
     prev = k
  end
  local new_args = {_orig = frame.args, _frame = frame, _next_key = next_key,
		    _preprocessed = {}}
  setmetatable(new_args, frame_args_meta)
  frame.args = new_args
  frame.argumentPairs = function (x) return pairs(x.args) end
  frame.getArgument = function(x, name)
    if type(name) == "table" then name = name.name end
    local v = x.args[name]
    if v == nil then return nil end
    return { expand = function() return v end }
  end
  frame.newChild = function(x, o)
    local title = (o and o.title) or ""
    local args = (o and o.args) or {}
    local new_frame = mw.clone(x)
    new_frame.getParent = function(ctx) return x end
    new_frame.getTitle = function(ctx) return title end
    new_frame.args = args
    prepare_frame_args(new_frame)
    return new_frame
  end
end

-- This function implements the {{#invoke:...}} parser function.  XXX
-- need better handling of parent frame and frame This returns (true,
-- value) if successful, (false, error) if exception.  NOTE: This can
-- be called from hostile code, but this is defined within the
-- sandbox, so the main risks come from the argument data structures
-- in calls from Python.  Python code must keep in mind that those
-- arguments and any functions and data structures in them can be
-- accessed, called, and modified by hostile code.
-- 20230711: #invoke should return a string, according to documentation
-- the return value from an invoked module function should be a string,
-- "otherwise all values are stringified and concatenated into a single
-- string". This doesn't exactly happen after testing it out on Wiktionary's
-- Sandbox: nil -> "", table -> "table" (literally), function -> "function",
-- the rest are stringified as normal and didn't test passing a thread or
-- "userdata" which I'm still not sure what it is.
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
            success, mod = pcall(initfn, _G)
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
            success, mod = pcall(initfn, _G)
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
   local st, v = pcall(fn, frame)
   -- print("Lua sandbox:", tostring(v))
   _mw_frame = saved_frame
   _mw_pageTitle = saved_pageTitle
   if type(v) == "string" then
      return st, v
   end
   if type(v) == "table" then
      return st, "table"
   end
   if v == nil then
      return st, ""
   end
   if type(v) == "function" then
      return st, "function"
   end
   return st, tostring(v)
end

-- This should be called immediately after loading the sandbox to set the
-- Python function that will be used for loading Lua modules and various
-- other Python functions that implement some of the functionality needed
-- for executing Scribunto code (these functions are called from Lua code).
local function _lua_set_functions(
        mw_text_decode, mw_text_encode, mw_text_jsonencode, mw_text_jsondecode,
        get_page_info, get_page_content, fetch_language_name,
        fetch_language_names, mw_wikibase_getlabel, mw_wikibase_getdesc
)
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
   mw_wikibase_getlabel_python = mw_wikibase_getlabel
   mw_wikibase_getdesc_python = mw_wikibase_getdesc

   -- This is set in https://github.com/wikimedia/mediawiki-extensions-Scribunto/blob/4aa17cb80c72998b9cead27e5be1ca39d8a0cfed/includes/Engines/LuaCommon/lualib/mw.language.lua#L27-L28
   -- and used in https://en.wiktionary.org/wiki/Module:languages
   string.uupper = mw.ustring.upper
   string.ulower = mw.ustring.lower
end


-- Change next() to use a new metamethod __next so that we can redefine it for
-- certain tables
function next(t, k)
   local m = getmetatable(t)
   local n = m and m.__next or _orig_next
   return n(t, k)
end

-- Add support of __pairs and __ipairs metamethods
-- https://www.mediawiki.org/wiki/LuaSandbox#Differences_from_standard_Lua
function pairs(t)
    local mt = getmetatable(t)
    if mt and mt.__pairs then
       return mt.__pairs(t)
    else
       return next, t, nil
    end
end

function ipairs(t)
    local mt = getmetatable(t)
    if mt and mt.__ipairs then
        return mt.__ipairs(t)
    else
        local function stateless_iter(tbl, i)
            i = i + 1
            local v = tbl[i]
            if nil~=v then return i, v end
        end
        return stateless_iter, t, 0
    end
end

-- Make sure we are operating in the restricted environment
assert(io == nil)
assert(_G.io == nil)

return { _lua_set_functions, _lua_invoke, _lua_reset_env }
