-- Make Lua's string library independent of the process locale.
--
-- Lua 5.1 classifies bytes with the C library (isspace(), isalpha(),
-- tolower(), ...) for the pattern classes %a %c %d %l %p %s %u %w %x and for
-- string.lower() and string.upper().  Those functions follow LC_CTYPE, which
-- Python sets from the environment at startup.  In a UTF-8 locale macOS
-- counts byte 0xA0 as a space and 0xE0 as a letter, and Windows code-page
-- locales lower-case bytes above 0x7F, so `%s`, `%a` and string.lower() cut
-- or change UTF-8 characters ("à" is C3 A0, "ム" is E3 83 A0) and later
-- mw.ustring calls fail with "string is not UTF-8".  MediaWiki's servers, and
-- Linux in any UTF-8 locale, classify only ASCII.
--
-- This replaces those functions with versions that give the C locale's
-- results: patterns are rewritten so that each class becomes an explicit set
-- of bytes, and lower()/upper() change only A-Z and a-z.

local concat = table.concat
local sub = string.sub
local type = type

local find = string.find
local match = string.match
local gmatch = string.gmatch
local gsub = string.gsub
local lower = string.lower
local upper = string.upper

-- The members of each class in the C locale, written as set items.  The
-- upper-case letters are the complements, which a set cannot negate.
local CLASS_ITEMS = {
    a = "A-Za-z",
    c = "%z\1-\31\127",
    d = "0-9",
    l = "a-z",
    p = "!-/:-@[-`{-~",
    s = "\t-\r ",
    u = "A-Z",
    w = "0-9A-Za-z",
    x = "0-9A-Fa-f",
    A = "%z\1-@[-`{-\255",
    C = " -~\128-\255",
    D = "%z\1-/:-\255",
    L = "%z\1-`{-\255",
    P = "%z\1- 0-9A-Za-z\127-\255",
    S = "%z\1-\8\14-\31!-\255",
    U = "%z\1-@[-\255",
    W = "%z\1-/:-@[-`{-\255",
    X = "%z\1-/:-@G-`g-\255",
}

-- A class outside a set becomes a set of its own.
local CLASS_SETS = {}
for letter, items in pairs(CLASS_ITEMS) do
    CLASS_SETS[letter] = "[" .. items .. "]"
end

-- Rewrites the set that starts at p[i] ("["), reading it the way lstrlib.c
-- does (classEnd() finds its end, matchbracketclass() reads its items).
-- Appends to out and returns the index after the set, or nil when the
-- pattern should be left as it is.
local function translate_set(p, i, out)
    local len = #p
    local j = i + 1
    if sub(p, j, j) == "^" then
        j = j + 1
    end
    repeat
        if j > len then
            return nil -- missing "]": let Lua report the malformed pattern
        end
        if sub(p, j, j) == "%" then
            j = j + 1
        end
        j = j + 1
    until sub(p, j, j) == "]"
    local ec = j

    local k = i + 1
    if sub(p, k, k) == "^" then
        out[#out + 1] = "[^"
        k = k + 1
    else
        out[#out + 1] = "["
    end
    while k < ec do
        local c = sub(p, k, k)
        if c == "%" then
            local d = sub(p, k + 1, k + 1)
            out[#out + 1] = CLASS_ITEMS[d] or ("%" .. d)
            k = k + 2
        elseif sub(p, k + 1, k + 1) == "-" and k + 2 < ec then
            if sub(p, k + 2, k + 2) == "%" then
                return nil -- a range ending in "%": too odd to rewrite
            end
            out[#out + 1] = sub(p, k, k + 2)
            k = k + 3
        elseif c == "-" then
            -- Escaped, so that it cannot form a range with the last byte
            -- of a class written just before it.
            out[#out + 1] = "%-"
            k = k + 1
        else
            out[#out + 1] = c
            k = k + 1
        end
    end
    out[#out + 1] = "]"
    return ec + 1
end

-- Returns pattern p with every character class written out as bytes.
local function translate(p)
    local out = {}
    local len = #p
    local i = 1
    while i <= len do
        local c = sub(p, i, i)
        if c == "%" then
            local d = sub(p, i + 1, i + 1)
            if d == "b" then
                out[#out + 1] = sub(p, i, i + 3) -- %bxy: x and y are bytes
                i = i + 4
            else
                out[#out + 1] = CLASS_SETS[d] or ("%" .. d)
                i = i + 2
            end
        elseif c == "[" then
            i = translate_set(p, i, out)
            if i == nil then
                return p
            end
        else
            out[#out + 1] = c
            i = i + 1
        end
    end
    return concat(out)
end

local cache = {}
local cache_size = 0

local function c_locale_pattern(p)
    if type(p) ~= "string" then
        return p -- a number, or an error the original function reports
    end
    local t = cache[p]
    if t == nil then
        t = p
        if find(p, "%", 1, true) then
            t = translate(p)
        end
        if cache_size >= 10000 then
            cache = {}
            cache_size = 0
        end
        cache[p] = t
        cache_size = cache_size + 1
    end
    return t
end

-- String metatables index this same table, so s:find() is covered too.
string.find = function(s, pattern, init, plain)
    if plain then
        return find(s, pattern, init, plain)
    end
    return find(s, c_locale_pattern(pattern), init)
end

string.match = function(s, pattern, init)
    return match(s, c_locale_pattern(pattern), init)
end

string.gmatch = function(s, pattern)
    return gmatch(s, c_locale_pattern(pattern))
end

string.gsub = function(s, pattern, repl, n)
    return gsub(s, c_locale_pattern(pattern), repl, n)
end

local TO_LOWER = {}
local TO_UPPER = {}
for b = 65, 90 do
    TO_LOWER[string.char(b)] = string.char(b + 32)
    TO_UPPER[string.char(b + 32)] = string.char(b)
end

string.lower = function(s)
    if type(s) == "string" and find(s, "[\128-\255]") then
        return (gsub(s, "[A-Z]", TO_LOWER))
    end
    return (lower(s))
end

string.upper = function(s)
    if type(s) == "string" and find(s, "[\128-\255]") then
        return (gsub(s, "[a-z]", TO_UPPER))
    end
    return (upper(s))
end

-- For tests.
return translate
