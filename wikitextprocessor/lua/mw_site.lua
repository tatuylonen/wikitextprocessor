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
}
Namespace.__index = Namespace

function Namespace:new(obj)
   obj = obj or {}
   setmetatable(obj, self)
   obj.canonicalName = obj.name
   obj.displayName = obj.name
   obj.hasSubpages = obj.name == NAMESPACE_TEXTS["Main"] or obj.name == NAMESPACE_TEXTS["Module"]
   return obj
end

-- These duplicate definitions in wikiparserfns.py
local media_ns = Namespace:new{id=-2, name=NAMESPACE_TEXTS["Media"], isSubject=true}
local special_ns = Namespace:new{id=-1, name=NAMESPACE_TEXTS["Special"], isSubject=true}
local main_ns = Namespace:new{id=0, name=NAMESPACE_TEXTS["Main"], isContent=true, isSubject=true}
local talk_ns = Namespace:new{id=1, name=NAMESPACE_TEXTS["Talk"], isTalk=true, subject=main_ns}
local user_ns = Namespace:new{id=2, name=NAMESPACE_TEXTS["User"], isSubject=true}
local user_talk_ns = Namespace:new{id=3, name=NAMESPACE_TEXTS["User talk"], isTalk=true, subject=user_ns}
local project_ns = Namespace:new{id=4, name=NAMESPACE_TEXTS["Project"], isSubject=true, aliases=NAMESPACE_ALIASES[NAMESPACE_TEXTS["Project"]]}
local project_talk_ns = Namespace:new{id=5, name=NAMESPACE_TEXTS["Project talk"], isTalk=true, subject=project_ns}
local file_ns = Namespace:new{id=6, name=NAMESPACE_TEXTS["File"], aliases=NAMESPACE_ALIASES["File"], isSubject=true}
local file_talk_ns = Namespace:new{id=7, name=NAMESPACE_TEXTS["File talk"], aliases=NAMESPACE_ALIASES["File talk"], isTalk=true, subject=file_ns}
local mediawiki_ns = Namespace:new{id=8, name=NAMESPACE_TEXTS["MediaWiki"], isSubject=true}
local mediawiki_talk_ns = Namespace:new{id=9, name=NAMESPACE_TEXTS["MediaWiki talk"],
                                        isTalk=true, subject=mediawiki_ns}
local template_ns = Namespace:new{id=10, name=NAMESPACE_TEXTS["Template"], isSubject=true, aliases=NAMESPACE_ALIASES["Template"]}
local template_talk_ns = Namespace:new{id=11, name=NAMESPACE_TEXTS["Template talk"], isTalk=true, subject=template_ns}
local help_ns = Namespace:new{id=12, name=NAMESPACE_TEXTS["Help"], isSubject=true}
local help_talk_ns = Namespace:new{id=13, name=NAMESPACE_TEXTS["Help talk"], isTalk=true, subject=help_ns}
local category_ns = Namespace:new{id=14, name=NAMESPACE_TEXTS["Category"], isSubject=true, aliases=NAMESPACE_ALIASES["Category"]}
local category_talk_ns = Namespace:new{id=15, name=NAMESPACE_TEXTS["Category talk"], isTalk=true, subject=category_ns}
local thread_ns = Namespace:new{id=90, name=NAMESPACE_TEXTS["Thread"], isSubject=true}
local thread_talk_ns = Namespace:new{id=91, name=NAMESPACE_TEXTS["Thread talk"], isTalk=true, subject=thread_ns}
local summary_ns = Namespace:new{id=92, name=NAMESPACE_TEXTS["Summary"], isSubject=true}
local summary_talk_ns = Namespace:new{id=93, name=NAMESPACE_TEXTS["Summary talk"], isTalk=true, subject=summary_ns}
local appendix_ns = Namespace:new{id=100, name=NAMESPACE_TEXTS["Appendix"], isSubject=true, aliases=NAMESPACE_ALIASES["Appendix"]}
local appendix_talk_ns = Namespace:new{id=101, name=NAMESPACE_TEXTS["Appendix talk"], isTalk=true, subject=appendix_ns}
local concordance_ns = Namespace:new{id=102, name=NAMESPACE_TEXTS["Concordance"], isSubject=true}
local concordance_talk_ns = Namespace:new{id=103, name=NAMESPACE_TEXTS["Concordance talk"], isTalk=true, subject=concordance_ns}
local index_ns = Namespace:new{id=104, name=NAMESPACE_TEXTS["Index"], isSubject=true}
local index_talk_ns = Namespace:new{id=105, name=NAMESPACE_TEXTS["Index talk"], isTalk=true, subject=index_ns}
local rhymes_ns = Namespace:new{id=106, name=NAMESPACE_TEXTS["Rhymes"], isSubject=true}
local rhymes_talk_ns = Namespace:new{id=107, name=NAMESPACE_TEXTS["Rhymes talk"], isTalk=true, subject=rhymes_ns}
local transwiki_ns = Namespace:new{id=108, name=NAMESPACE_TEXTS["Transwiki"], isSubject=true}
local transwiki_talk_ns = Namespace:new{id=109, name=NAMESPACE_TEXTS["Transwiki talk"], isTalk=true, subject=transwiki_ns}
local thesaurus_ns = Namespace:new{id=110, name=NAMESPACE_TEXTS["Thesaurus"], isSubject=true, aliases=NAMESPACE_ALIASES["Thesaurus"]}
local thesaurus_talk_ns = Namespace:new{id=111, name=NAMESPACE_TEXTS["Thesaurus talk"], isTalk=true, subject=thesaurus_ns, aliases=NAMESPACE_ALIASES["Thesaurus talk"]}
local citations_ns = Namespace:new{id=114, name=NAMESPACE_TEXTS["Citations"], isSubject=true}
local citations_talk_ns = Namespace:new{id=115, name=NAMESPACE_TEXTS["Citations talk"], isTalk=true, subject=citations_ns}
local sign_gloss_ns = Namespace:new{id=116, name=NAMESPACE_TEXTS["Sign gloss"], isSubject=true}
local sign_gloss_talk_ns = Namespace:new{id=117, name=NAMESPACE_TEXTS["Sign gloss talk"], isTalk=true, subject=sign_gloss_ns}
local reconstruction_ns = Namespace:new{id=118, name=NAMESPACE_TEXTS["Reconstruction"], isSubject=true, aliases=NAMESPACE_ALIASES["Reconstruction"]}
local reconstruction_talk_ns = Namespace:new{id=119, name=NAMESPACE_TEXTS["Reconstruction talk"], isTalk=true, subject=reconstruction_ns}
local module_ns = Namespace:new{id=828, name=NAMESPACE_TEXTS["Module"], isIncludable=true, isSubject=true, aliases=NAMESPACE_ALIASES["Module"]}
local module_talk_ns = Namespace:new{id=829, name=NAMESPACE_TEXTS["Module talk"], isTalk=true, subject=module_ns}

main_ns.talk = talk_ns
user_ns.talk = user_talk_ns
project_ns.talk = project_talk_ns
file_ns.talk = file_talk_ns
mediawiki_ns.talk = mediawiki_talk_ns
template_ns.talk = template_talk_ns
help_ns.talk = help_talk_ns
category_ns.talk = category_talk_ns
thread_ns.talk = thread_talk_ns
summary_ns.talk = summary_talk_ns
appendix_ns.talk = appendix_talk_ns
concordance_ns.talk = concordance_talk_ns
index_ns.talk = index_talk_ns
rhymes_ns.talk = rhymes_talk_ns
transwiki_ns.talk = transwiki_talk_ns
thesaurus_ns.talk = thesaurus_talk_ns
citations_ns.talk = citations_talk_ns
sign_gloss_ns.talk = sign_gloss_talk_ns
reconstruction_ns.talk = reconstruction_talk_ns
module_ns.talk = module_talk_ns

local function add_ns(t, ns)
   assert(ns.name ~= nil)
   assert(ns.id ~= nil)
   t[ns.id] = ns
   t[ns.name] = ns
end

local mw_site_namespaces = {}
add_ns(mw_site_namespaces, media_ns)
add_ns(mw_site_namespaces, special_ns)
add_ns(mw_site_namespaces, main_ns)
add_ns(mw_site_namespaces, talk_ns)
add_ns(mw_site_namespaces, user_ns)
add_ns(mw_site_namespaces, user_talk_ns)
add_ns(mw_site_namespaces, project_ns)
add_ns(mw_site_namespaces, project_talk_ns)
add_ns(mw_site_namespaces, file_ns)
add_ns(mw_site_namespaces, file_talk_ns)
add_ns(mw_site_namespaces, mediawiki_ns)
add_ns(mw_site_namespaces, mediawiki_talk_ns)
add_ns(mw_site_namespaces, template_ns)
add_ns(mw_site_namespaces, template_talk_ns)
add_ns(mw_site_namespaces, help_ns)
add_ns(mw_site_namespaces, help_talk_ns)
add_ns(mw_site_namespaces, category_ns)
add_ns(mw_site_namespaces, category_talk_ns)
add_ns(mw_site_namespaces, thread_ns)
add_ns(mw_site_namespaces, thread_talk_ns)
add_ns(mw_site_namespaces, summary_ns)
add_ns(mw_site_namespaces, summary_talk_ns)
add_ns(mw_site_namespaces, appendix_ns)
add_ns(mw_site_namespaces, appendix_talk_ns)
add_ns(mw_site_namespaces, concordance_ns)
add_ns(mw_site_namespaces, concordance_talk_ns)
add_ns(mw_site_namespaces, rhymes_ns)
add_ns(mw_site_namespaces, rhymes_talk_ns)
add_ns(mw_site_namespaces, transwiki_ns)
add_ns(mw_site_namespaces, transwiki_talk_ns)
add_ns(mw_site_namespaces, thesaurus_ns)
add_ns(mw_site_namespaces, thesaurus_talk_ns)
add_ns(mw_site_namespaces, citations_ns)
add_ns(mw_site_namespaces, citations_talk_ns)
add_ns(mw_site_namespaces, sign_gloss_ns)
add_ns(mw_site_namespaces, sign_gloss_talk_ns)
add_ns(mw_site_namespaces, reconstruction_ns)
add_ns(mw_site_namespaces, reconstruction_talk_ns)
add_ns(mw_site_namespaces, module_ns)
add_ns(mw_site_namespaces, module_talk_ns)

local mw_site_contentNamespaces = {}
add_ns(mw_site_contentNamespaces, main_ns)
add_ns(mw_site_contentNamespaces, appendix_ns)
add_ns(mw_site_contentNamespaces, thesaurus_ns)
add_ns(mw_site_contentNamespaces, reconstruction_ns)

local mw_site_subjectNamespaces = {}
add_ns(mw_site_subjectNamespaces, media_ns)
add_ns(mw_site_subjectNamespaces, special_ns)
add_ns(mw_site_subjectNamespaces, main_ns)
add_ns(mw_site_subjectNamespaces, user_ns)
add_ns(mw_site_subjectNamespaces, project_ns)
add_ns(mw_site_subjectNamespaces, file_ns)
add_ns(mw_site_subjectNamespaces, mediawiki_ns)
add_ns(mw_site_subjectNamespaces, template_ns)
add_ns(mw_site_subjectNamespaces, help_ns)
add_ns(mw_site_subjectNamespaces, category_ns)
add_ns(mw_site_subjectNamespaces, thread_ns)
add_ns(mw_site_subjectNamespaces, summary_ns)
add_ns(mw_site_subjectNamespaces, appendix_ns)
add_ns(mw_site_subjectNamespaces, thesaurus_ns)
add_ns(mw_site_subjectNamespaces, concordance_ns)
add_ns(mw_site_subjectNamespaces, index_ns)
add_ns(mw_site_subjectNamespaces, rhymes_ns)
add_ns(mw_site_subjectNamespaces, transwiki_ns)
add_ns(mw_site_subjectNamespaces, thesaurus_ns)
add_ns(mw_site_subjectNamespaces, citations_ns)
add_ns(mw_site_subjectNamespaces, sign_gloss_ns)
add_ns(mw_site_subjectNamespaces, reconstruction_ns)
add_ns(mw_site_subjectNamespaces, module_ns)

local mw_site_talkNamespaces = {}
add_ns(mw_site_talkNamespaces, talk_ns)
add_ns(mw_site_talkNamespaces, user_talk_ns)
add_ns(mw_site_talkNamespaces, project_talk_ns)
add_ns(mw_site_talkNamespaces, file_talk_ns)
add_ns(mw_site_talkNamespaces, mediawiki_talk_ns)
add_ns(mw_site_talkNamespaces, template_talk_ns)
add_ns(mw_site_talkNamespaces, help_talk_ns)
add_ns(mw_site_talkNamespaces, category_talk_ns)
add_ns(mw_site_talkNamespaces, thread_talk_ns)
add_ns(mw_site_talkNamespaces, summary_talk_ns)
add_ns(mw_site_talkNamespaces, appendix_talk_ns)
add_ns(mw_site_talkNamespaces, concordance_talk_ns)
add_ns(mw_site_talkNamespaces, index_talk_ns)
add_ns(mw_site_talkNamespaces, rhymes_talk_ns)
add_ns(mw_site_talkNamespaces, transwiki_talk_ns)
add_ns(mw_site_talkNamespaces, thesaurus_talk_ns)
add_ns(mw_site_talkNamespaces, citations_talk_ns)
add_ns(mw_site_talkNamespaces, sign_gloss_talk_ns)
add_ns(mw_site_talkNamespaces, reconstruction_talk_ns)
add_ns(mw_site_talkNamespaces, module_talk_ns)

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
   print("mw.site.interwikiMap called", filter)
   return {}
end

return mw_site
