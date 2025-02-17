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
    ext = "mw_ext",
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
    -- https://github.com/wikimedia/mediawiki-extensions-Scribunto/blob/184216759e22635bd25a0844e6f68979ecf7bc2a/includes/Engines/LuaCommon/lualib/mw.lua#L551
    local doneTable = {}
    local doneObj = {}
    local ct = {}
    local function sorter( a, b )
        local ta, tb = type( a ), type( b )
        if ta ~= tb then
            return ta < tb
        end
        if ta == 'string' or ta == 'number' then
            return a < b
        end
        if ta == 'boolean' then
            return tostring( a ) < tostring( b )
        end
        return false -- Incomparable
    end
    local function _dumpObject( object, indent, expandTable )
        local tp = type( object )
        if tp == 'number' or tp == 'nil' or tp == 'boolean' then
            return tostring( object )
        elseif tp == 'string' then
            return string.format( "%q", object )
        elseif tp == 'table' then
            if not doneObj[object] then
                local s = tostring( object )
                if string.sub(s, 1, 6) == 'table:' then  -- this line changed
                    ct[tp] = ( ct[tp] or 0 ) + 1
                    doneObj[object] = 'table#' .. ct[tp]
                else
                    doneObj[object] = s
                    doneTable[object] = true
                end
            end
            if doneTable[object] or not expandTable then
                return doneObj[object]
            end
            doneTable[object] = true

            local ret = { doneObj[object], ' {\n' }
            local mt = getmetatable( object )
            local indentString = "  "
            if mt then
                ret[#ret + 1] = string.rep( indentString, indent + 2 )
                ret[#ret + 1] = 'metatable = '
                ret[#ret + 1] = _dumpObject( mt, indent + 2, false )
                ret[#ret + 1] = "\n"
            end

            local doneKeys = {}
            for key, value in ipairs( object ) do
                doneKeys[key] = true
                ret[#ret + 1] = string.rep( indentString, indent + 2 )
                ret[#ret + 1] = _dumpObject( value, indent + 2, true )
                ret[#ret + 1] = ',\n'
            end
            local keys = {}
            for key in pairs( object ) do
                if not doneKeys[key] then
                    keys[#keys + 1] = key
                end
            end
            table.sort( keys, sorter )
            for i = 1, #keys do
                local key = keys[i]
                ret[#ret + 1] = string.rep( indentString, indent + 2 )
                ret[#ret + 1] = '['
                ret[#ret + 1] = _dumpObject( key, indent + 3, false )
                ret[#ret + 1] = '] = '
                ret[#ret + 1] = _dumpObject( object[key], indent + 2, true )
                ret[#ret + 1] = ",\n"
            end
            ret[#ret + 1] = string.rep( indentString, indent )
            ret[#ret + 1] = '}'
            return table.concat( ret )
        else
            if not doneObj[object] then
                ct[tp] = ( ct[tp] or 0 ) + 1
                doneObj[object] = tostring( object ) .. '#' .. ct[tp]
            end
            return doneObj[object]
        end
    end
    return _dumpObject( obj, 0, true )
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

function mw.loadJsonData(page)
    return _new_loadJsonData(page)
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
