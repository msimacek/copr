/*-
 * Copyright (c) 2014 Red Hat, Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.fedoraproject.copr.client.impl;

import java.lang.reflect.Type;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.reflect.TypeToken;

import org.fedoraproject.copr.client.BuildRequest;
import org.fedoraproject.copr.client.BuildResult;

/**
 * @author Mikolaj Izdebski
 */
public class BuildCommand
    extends RpcCommand<BuildResult>
{
    private final BuildRequest request;

    public BuildCommand( BuildRequest request )
    {
        this.request = request;
    }

    @Override
    protected boolean requiresAuthentication()
    {
        return true;
    }

    @Override
    protected String getCommandUrl()
    {
        return "/api/coprs/" + request.getUserName() + "/" + request.getProjectName() + "/new_build/";
    }

    @Override
    protected Map<String, String> getExtraArguments()
    {
        Map<String, String> map = new LinkedHashMap<>();

        StringBuilder sb = new StringBuilder();

        for ( String url : request.getSourceRpmList() )
        {
            if ( sb.length() > 0 )
                sb.append( ' ' );
            sb.append( url );
        }

        map.put( "pkgs", sb.toString() );

        if ( request.getMemory() != null )
        {
            map.put( "memory", request.getMemory() );
        }

        if ( request.getTimeout() != null )
        {
            map.put( "timeout", request.getTimeout() );
        }

        return map;
    }

    @Override
    protected BuildResult parseResponse( JsonObject response )
    {
        JsonArray idsArray = response.get( "ids" ).getAsJsonArray();
        Type type = new TypeToken<List<Long>>()
        {
        }.getType();
        List<Long> buildIds = new Gson().fromJson( idsArray, type );
        String message = response.get( "message" ).getAsString();

        return new DefaultBuildResult( buildIds, message );
    }
}
