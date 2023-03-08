-- Simplified implementation of mw.site for running WikiMedia Scribunto
-- code under Python
--
-- Copyright (c) 2020-2021 Tatu Ylonen.  See file LICENSE and https://ylonen.org

local Namespace = {
   hasGenderDistinction = true,
   isCapitalized = false,
   isMovable = false,
   defaultContentModel = "wikitext",
   aliases = {},
   associated = {},
   isSubject = false,
   isTalk = false,
   isContent = false,
   talk = nil,
   subject = nil
}
Namespace.__index = Namespace

function Namespace:new(obj)
   obj = obj or {}
   setmetatable(obj, self)
   obj.canonicalName = obj.name
   obj.displayName = obj.name
   obj.hasSubpages = obj.name == "Main" or obj.name == NAMESPACE_DATA.Module.name
   return obj
end

-- These duplicate definitions in wikiparserfns.py
local mw_site_namespaces = {}
local mw_site_contentNamespaces = {}
local mw_site_subjectNamespaces = {}
local mw_site_talkNamespaces = {}

for ns_canonical_name in pairs(NAMESPACE_DATA) do
  local ns_data = NAMESPACE_DATA[ns_canonical_name]
  local ns = Namespace:new{
    id=ns_data.id,
    name=ns_data.name,
    isSubject=ns_data.issubject,
    isContent=ns_data.content,
    isTalk=ns_data.istalk,
    aliases=ns_data.aliases
  }
  mw_site_namespaces[ns_data.id] = ns
  mw_site_namespaces[ns_data.name] = ns

  if ns_data.content then
    mw_site_contentNamespaces[ns_data.id] = ns
    mw_site_contentNamespaces[ns_data.name] = ns
  end
  if ns_data.issubject then
    mw_site_subjectNamespaces[ns_data.id] = ns
    mw_site_subjectNamespaces[ns_data.name] = ns
  end
  if ns_data.istalk then
    mw_site_talkNamespaces[ns_data.id] = ns
    mw_site_talkNamespaces[ns_data.name] = ns
  end
end

for ns_id in pairs(mw_site_namespaces) do
  if type(ns_id) == "number" then
    if mw_site_namespaces[ns_id].isSubject and ns_id >= 0 then
      mw_site_namespaces[ns_id].talk = mw_site_namespaces[ns_id + 1]
    end
    if mw_site_namespaces[ns_id].isTalk then
      mw_site_namespaces[ns_id].subject = mw_site_namespaces[ns_id - 1]
    end
  end
end


local function mw_site_index(x, ns)
   return mw.site.findNamespace(ns)
end

local mw_site = {
   __index = mw_site_index,
   server = "server.dummy",
   siteName = "Dummy Site",
   namespaces = mw_site_namespaces,
   contentNamespaces = mw_site_contentNamespaces,
   subjectNamespaces = mw_site_subjectNamespaces,
   talkNamespaces = mw_site_talkNamespaces,
   stats = {
      pages = 0,
      articles = 0,
      files = 0,
      users = 0,
      activeUsers = 0,
      admins = 0
   }
}

function mw_site.matchNamespaceName(v, name)
   -- Internal function to match namespace against name
   -- namespace prefixes are case-insensitive
   if type(name) == "number" then
      if name == v.id then return true end
      return false
   end
   assert(type(name) == "string")
   name = mw.ustring.upper(name)
   if name == mw.ustring.upper(v.name) then return true end
   if name == mw.ustring.upper(v.canonicalName) then return true end
   for i, alias in ipairs(v.aliases) do
      if name == mw.ustring.upper(alias) then return true end
   end
   return false
end

function mw_site.findNamespace(name)
   -- Internal function to find the namespace object corresponding to a name
   if type(name) == "string" then
      -- strip surrounding whitespaces
      name = name:gsub("^%s(.-)%s*$", "%1")
   end
   for k, v in pairs(mw.site.namespaces) do
      if mw.site.matchNamespaceName(v, name) then
         return v
      end
   end
   return nil
end

function mw_site.stats.pagesInCategory(category, which)
   if which == "*" or which == nil then
      return {
         all = 0,
         subcats = 0,
         files = 0,
         pages = 0
      }
   end
   return 0
end

function mw_site.stats.pagesInNamespace(ns)
   return 0
end

function mw_site.stats.usersInGroup(filter)
   return 0
end

function mw_site.interwikiMap(filter)
   -- print("mw.site.interwikiMap called", filter)
   return {}
end

return mw_site
