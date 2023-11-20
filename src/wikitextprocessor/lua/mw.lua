-- Simplified implementation of mw for running WikiMedia Scribunto code
-- under Python
--
-- Copyright (c) 2020-2021 Tatu Ylonen.  See file LICENSE and https://ylonen.org

local mw_autoload = {
    hash = "mw_hash",
    html = "mw_html",
    language = "mw_language",
    site = "mw_site",
    text = "mw_text",
    title = "mw_title",
    uri = "mw_uri",
    ustring = "ustring:ustring",
    wikibase = "mw_wikibase",
    message = "mw_message",
    getContentLanguage = function(table)
        return table.language.getContentLanguage
    end,
    getLanguage = function(table)
        return table.language.getContentLanguage
    end
}

local mw_meta = {}

-- This is intentionally a global variable, as this is accessed by many modules
mw = {
    -- addWarning  (see below)
    -- allToString  (see below)
    -- clone  (see below)
    -- dumpObject  (see below)
    -- getCurrentFrame -- assigned in lua_invoke for each call
    -- hash - autoloaded
    -- html - autoloaded
    -- incrementExpensiveFunctionCount (see below)
    -- isSubsting  (see below)
    -- language - autoloaded
    -- loadData  (see below)
    -- log  (see below)
    -- logObject  (see below)
    -- XXX message.*
    -- site - autoloaded
    -- text - autoloaded
    -- title - autoloaded
    -- uri - autoloaded
    -- ustring - autoloaded
}
setmetatable(mw, mw_meta)

function mw_meta.__index(table, key)
    local modname = mw_autoload[key]
    if modname == nil then return nil end
    local ret
    if type(modname) == "string" then
        ret = require(modname)
    elseif type(modname) == "function" then
        ret = modname(table)
    else
        error("mw_meta.__index had modname", modname)
    end
    table[key] = ret
    return ret
end

function mw.addWarning(text)
    print("mw.addWarning", text)
end

function mw.allToString(...)
    local ret = ""
    for k, v in pairs(...) do
        ret = ret .. tostring(v)
    end
    return ret
end

function mw.clone(v)
    local ret = _mw_clone(v)
    -- print("mw_clone: " .. tostring(ret))
    return ret
end

function mw.dumpObject(obj)
    print("mw.dumpObject", obj)
end

function mw.incrementExpensiveFunctionCount()
    print("mw.incrementExpensiveFunctionCount")
end

function mw.isSubsting()
    return false
end

-- mw.loadData function - loads a data file.  This is same as require(),
-- which already implements caching.
function mw.loadData(modname)
    return _new_loadData(modname)
end

function mw.log(...)
    -- print("mw.log", ...)
end

function mw.logObject(obj)
    -- print("mw.logObject", obj)
end

function mw.getCurrentFrame()
    return current_frame_python()
end

return mw
